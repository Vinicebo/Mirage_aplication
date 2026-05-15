import json
import os
import csv
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError


# =============================================================================
# 🛠️ CONFIGURATION SECTION - EDIT HERE FOR YOUR SETUP
# =============================================================================
@dataclass
class APIConfig:
    """
    Central configuration for all APIs. Free tiers only.
    - NewsAPI: Get free key at https://newsapi.org/ (1000 req/month)
    - BrasilAPI: Free, no key
    - RSS: Free public feeds
    - IBGE: Free public API
    """
    news_api_key: str = "183cc74a2ad444b7939cf2723b731a91"  # Replace with your key
    brasil_api_enabled: bool = True
    rss_enabled: bool = True
    economic_enabled: bool = True
    cache_dir: str = "cache"
    default_queries: List[str] = field(default_factory=lambda: [
        "nova sede Rio de Janeiro",
        "expansão escritório Rio de Janeiro",
        "investimento corporativo Rio",
        "inauguração escritório Rio",
        "novo escritório Rio de Janeiro",
        "mudança sede corporativa Rio"
    ])

    def __post_init__(self):
        """Auto-enable NewsAPI if key provided. Create cache dir."""
        self.news_enabled = bool(self.news_api_key.strip())
        os.makedirs(self.cache_dir, exist_ok=True)


# MIRAGE INDUSTRIES (for fit scoring)
MIRAGE_INDUSTRIES = [
    'tech', 'finance', 'healthcare', 'legal', 'consulting',
    'retail', 'oil_gas', 'construction_re', 'manufacturing', 'other'
]
PERFECT_FITS = ['tech', 'finance', 'healthcare', 'legal', 'consulting']


# =============================================================================
# 💾 CACHING UTILITIES (file-based JSON, 24h TTL)
# =============================================================================
def get_cache_path(config: APIConfig, key: str) -> str:
    return os.path.join(config.cache_dir, f"{key}.json")

def load_cache(config: APIConfig, key: str, ttl_hours: int = 24) -> Optional[List[Dict]]:
    path = get_cache_path(config, key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        timestamp = datetime.fromisoformat(data['timestamp'])
        if datetime.now() - timestamp > timedelta(hours=ttl_hours):
            return None
        return data['data']
    except:
        return None

def save_cache(config: APIConfig, key: str, data: List[Dict]):
    path = get_cache_path(config, key)
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'data': data
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2)


# =============================================================================
# 🌐 API CLIENTS (Modular, Graceful Degradation)
# =============================================================================
class NewsAPIClient:
    """Client for NewsAPI.org - Detects corporate triggers in Rio news."""

    def __init__(self, config: APIConfig):
        self.config = config
        self.base_url = "https://newsapi.org/v2/everything"

    def search_triggers(self, days_back: int = 30) -> List[Dict]:
        """Search for trigger news. Returns list of events or []. Cache aware."""
        cache = load_cache(self.config, "news_triggers")
        if cache is not None:
            return cache
        if not self.config.news_enabled:
            return []
        results = []
        from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        headers = {'User-Agent': 'MirageBot/2.0'}
        for query in self.config.default_queries:
            params = {
                'q': query,
                'from': from_date,
                'sortBy': 'publishedAt',
                'language': 'pt',
                'pageSize': 10,
                'apiKey': self.config.news_api_key
            }
            url = self.base_url + '?' + urllib.parse.urlencode(params)
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    for article in data.get('articles', []):
                        trigger = self._parse_article_to_trigger(article)
                        if trigger:
                            results.append(trigger)
            except Exception as e:
                print(f"NewsAPI error for '{query}': {e}")
                continue
        # Deduplicate
        seen = set((r['company'].lower(), r['trigger_type']) for r in results)
        unique = [r for r in results if (r['company'].lower(), r['trigger_type']) not in seen]
        save_cache(self.config, "news_triggers", unique)
        return unique

    def _parse_article_to_trigger(self, article: Dict) -> Optional[Dict]:
        title = (article.get('title', '') + ' ' + article.get('description', '')).lower()
        trigger_types = {
            'nova sede': 'new_office',
            'expansão': 'expansion',
            'escritório': 'office',
            'investimento': 'investment',
            'inauguração': 'inauguration',
            'mudança sede': 'relocation'
        }
        trigger_type = None
        for kw, typ in trigger_types.items():
            if kw in title:
                trigger_type = typ
                break
        if not trigger_type:
            return None
        company = article.get('title', 'Unknown').split(' - ')[0].strip()
        return {
            'company': company,
            'trigger_type': trigger_type,
            'url': article.get('url', ''),
            'date': article.get('publishedAt', ''),
            'source': article.get('source', {}).get('name', 'Unknown')
        }


class BrasilAPIClient:
    """Client for BrasilAPI.com.br - Enriches company data from CNPJ."""

    def __init__(self, config: APIConfig):
        self.config = config
        self.base_url = "https://brasilapi.com.br/api/cnpj/v1"

    def enrich_company(self, cnpj: str) -> Optional[Dict]:
        """Fetch and map company data. Returns None on failure. Cache aware."""
        clean_cnpj = cnpj.replace('/', '_').replace('-', '_').replace('.', '_')
        cache_key = f"company_{clean_cnpj}"
        cache = load_cache(self.config, cache_key)
        if cache is not None:
            return cache[0] if cache else None
        if not self.config.brasil_api_enabled:
            return None
        url = f"{self.base_url}/{cnpj}"
        headers = {'User-Agent': 'MirageBot/2.0'}
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                enriched = self._map_to_mirage(data)
                save_cache(self.config, cache_key, [enriched])
                return enriched
        except HTTPError as e:
            if e.code == 404:
                pass  # Invalid CNPJ
        except Exception as e:
            print(f"BrasilAPI error for {cnpj}: {e}")
        return None

    def _map_to_mirage(self, data: Dict) -> Dict:
        cnae_code = data.get('atividade_principal', {}).get('code', '')[:2]
        industry_map = {
            '64': 'finance', '62': 'tech', '69': 'legal', '86': 'healthcare',
            '70': 'consulting', '47': 'retail', '06': 'oil_gas', '41': 'construction_re',
            '31': 'manufacturing'
        }
        industry = industry_map.get(cnae_code, 'other')
        capital = data.get('capital_social', 0) or 0
        return {
            'name': data.get('razao_social', ''),
            'industry': industry,
            'location': data.get('uf', ''),
            'employee_count_estimate': min(1000, capital / 10000),
            'estimated_budget_brl': capital / 10,
            'cnpj': data.get('cnpj', '')
        }


class BidScraperClient:
    """RSS scraper for public procurement bids (furniture in RJ)."""

    def __init__(self, config: APIConfig):
        self.config = config
        self.rss_urls = [
            "https://www.gov.br/compras/pt-br/rss.xml",  # Federal licitações
            # Add RJ-specific: e.g., "https://www.licitacoes-e-concursos.rj.gov.br/rss"
        ]

    def discover_bids(self) -> List[Dict]:
        """Parse RSS for furniture bids. Returns [] if none. Cache aware."""
        cache = load_cache(self.config, "bids")
        if cache is not None:
            return cache
        results = []
        if not self.config.rss_enabled:
            return results
        for url in self.rss_urls:
            bids = self._parse_rss(url)
            results.extend(bids)
        save_cache(self.config, "bids", results)
        return results

    def _parse_rss(self, url: str) -> List[Dict]:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                tree = ET.parse(resp)
                root = tree.getroot()
                items = []
                for item in root.findall('.//item'):
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    if title_elem is not None:
                        title = title_elem.text.lower()
                        if any(kw in title for kw in ['móveis', 'mobilia', 'furniture', 'escritório']):
                            items.append({
                                'company': title.split(' - ')[0] if ' - ' in title else 'Public Entity',
                                'bid_title': title_elem.text,
                                'url': link_elem.text if link_elem is not None else ''
                            })
                return items
        except Exception as e:
            print(f"RSS parse error for {url}: {e}")
        return []


class EconomicDataClient:
    """Fetches RJ economic indicators for seasonal adjustment."""

    def __init__(self, config: APIConfig):
        self.config = config

    def get_rj_economic_indicator(self) -> Dict:
        """Get seasonal factor (e.g., 1.2 for growth). Cache aware."""
        cache = load_cache(self.config, "economic_rj")
        if cache is not None:
            return cache[0]
        if not self.config.economic_enabled:
            return {'seasonal_factor': 1.0}
        # IBGE PIB per capita RJ latest
        url = "https://servicodados.ibge.gov.br/api/v3/agregados/593/periodos/%5B2024-01%5D/variaveis/2266?localidades=N2%5B35%5D"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                # Simplistic: assume growth
                factor = 1.15
                result = {'seasonal_factor': factor, 'data': data}
                save_cache(self.config, "economic_rj", [result])
                return result
        except Exception as e:
            print(f"Economic API error: {e}")
        return {'seasonal_factor': 1.0}


# =============================================================================
# 🎯 SCORING ENGINE (Preserved from v1, Enhanced)
# =============================================================================
def score_lead(lead: Dict, seasonal_factor: float = 1.0) -> Dict:
    """
    Scores lead on Fit, Size, Urgency. Total out of ~30.
    Tier: A(>=25), B(>=18), C(<18)
    """
    score = {'fit': 0, 'size': 0, 'urgency': 0, 'total': 0, 'tier': 'C', 'notes': []}

    # Fit (industry match)
    industry = lead.get('industry', 'other')
    if industry in PERFECT_FITS:
        score['fit'] = 10
    elif industry in MIRAGE_INDUSTRIES:
        score['fit'] = 7
    else:
        score['fit'] = 3

    # Size (employees or estimate)
    emp = lead.get('employee_count', 0) or lead.get('employee_count_estimate', 0)
    if emp > 500:
        score['size'] = 10
    elif emp > 100:
        score['size'] = 7
    elif emp > 20:
        score['size'] = 4
    else:
        score['size'] = 1

    # Urgency (triggers + seasonal)
    urgency = 5
    if lead.get('has_recent_trigger'):
        urgency += 5
    score['urgency'] = urgency * seasonal_factor

    score['total'] = score['fit'] + score['size'] + score['urgency']
    if score['total'] >= 25:
        score['tier'] = 'A'
    elif score['total'] >= 18:
        score['tier'] = 'B'

    # Notes
    if lead.get('has_recent_trigger'):
        score['notes'].append("Recent trigger")
    if lead.get('referral_source') == 'auto_detected':
        score['notes'].append("Auto-discovered")
    score['seasonal_factor'] = seasonal_factor

    return score


def score_architect(arch: Dict) -> float:
    """Score architect: past deals *2 + momentum*10."""
    past = arch.get('past_deals_mirage', 0)
    momentum = arch.get('recent_momentum', 0)
    return past * 2 + momentum * 10


def calculate_total_scores(leads: List[Dict], seasonal_factor: float = 1.0) -> List[Dict]:
    """Score all leads and sort by total descending."""
    for lead in leads:
        lead['score'] = score_lead(lead, seasonal_factor)
    leads.sort(key=lambda l: l['score']['total'], reverse=True)
    return leads


# =============================================================================
# 🤖 AUTOMATION PIPELINE
# =============================================================================
def load_leads(filepath: str = "leads.json") -> List[Dict]:
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_leads(leads: List[Dict], filepath: str = "leads.json"):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(leads, f, indent=2)

def auto_detect_triggers(leads: List[Dict], news_client: NewsAPIClient) -> List[Dict]:
    """Update leads with news triggers, create new candidates."""
    triggers = news_client.search_triggers()
    lead_names = {l['name'].lower(): l for l in leads}
    updated, new_leads = 0, []
    for trigger in triggers:
        company_lower = trigger['company'].lower()
        matched = None
        for name_lower, lead in lead_names.items():
            if company_lower in name_lower or name_lower in company_lower:
                matched = lead
                break
        if matched:
            matched['has_recent_trigger'] = True
            matched.setdefault('notes', []).append(f"News: {trigger['trigger_type']} [{trigger['url'][:50]}...]")
            updated += 1
        else:
            new_lead = {
                'name': trigger['company'],
                'industry': 'unknown',
                'employee_count': 0,
                'location': 'Rio de Janeiro',
                'has_recent_trigger': True,
                'notes': [f"Auto-detected news: {trigger['trigger_type']} - {trigger['source']} ({trigger['url']})"],
                'referral_source': 'auto_detected',
                'cnpj': None
            }
            new_leads.append(new_lead)
    print(f"Triggers: Updated {updated} leads, created {len(new_leads)} new.")
    return new_leads

def auto_enrich_company(leads: List[Dict], brasil_client: BrasilAPIClient) -> int:
    """Enrich leads missing data via CNPJ."""
    enriched = 0
    for lead in leads:
        if lead.get('cnpj') and not lead.get('industry'):
            data = brasil_client.enrich_company(lead['cnpj'])
            if data:
                lead.update(data)
                enriched += 1
    print(f"Enriched {enriched} companies via BrasilAPI.")
    return enriched

def auto_discover_leads(bid_client: BidScraperClient) -> List[Dict]:
    """Discover new leads from bids."""
    bids = bid_client.discover_bids()
    new_leads = []
    for bid in bids:
        new_lead = {
            'name': bid['company'],
            'industry': 'public_procurement',
            'employee_count': 100,  # proxy
            'location': 'Rio de Janeiro',
            'has_recent_trigger': True,
            'notes': [f"Bid opportunity: {bid['bid_title']} ({bid['url']})"],
            'referral_source': 'auto_detected_bid',
            'cnpj': None
        }
        new_leads.append(new_lead)
    print(f"Discovered {len(new_leads)} bid leads.")
    return new_leads

def run_fully_automated(config: APIConfig, leads: List[Dict], architects: List[Dict]):
    """Full v2 pipeline: APIs + scoring. Graceful if APIs fail."""
    news_client = NewsAPIClient(config)
    brasil_client = BrasilAPIClient(config)
    bid_client = BidScraperClient(config)
    econ_client = EconomicDataClient(config)

    seasonal = econ_client.get_rj_economic_indicator()['seasonal_factor']

    # Auto-detect & enrich
    new_news = auto_detect_triggers(leads, news_client)
    leads.extend(new_news)
    auto_enrich_company(leads, brasil_client)
    new_bids = auto_discover_leads(bid_client)
    leads.extend(new_bids)

    # Score
    calculate_total_scores(leads, seasonal)
    for arch in architects:
        arch['score'] = score_architect(arch)

    save_leads(leads)
    return leads, architects, seasonal

def run_semi_automated(leads: List[Dict], architects: List[Dict], seasonal: float = 1.0):
    """v1-compatible: Scoring only, no APIs."""
    calculate_total_scores(leads, seasonal)
    for arch in architects:
        arch['score'] = score_architect(arch)
    return leads, architects


# =============================================================================
# 📊 REPORTING (Enhanced from v1)
# =============================================================================
def generate_monthly_report(leads: List[Dict], architects: List[Dict]) -> str:
    """Beautiful console report with tiers and recommendations."""
    if not leads:
        return "No leads to report."
    seasonal = leads[0]['score']['seasonal_factor']

    report = "=== 🏢 MIRAGE MÓVEIS - MONTHLY CLIENT RECOMMENDATIONS v2 ===\n\n"

    # Top A-leads
    a_leads = [l for l in leads if l['score']['tier'] == 'A'][:5]
    report += "🏆 A-LEADS (Prioridade Máxima):\n"
    for lead in a_leads:
        notes = ', '.join(lead['score']['notes']) or 'N/A'
        report += f"  • {lead['name']} ({lead['industry'].title()}, {lead['location']}) | {lead['score']['total']:.1f}pts | {notes}\n"

    # Tier counts
    tiers = {'A': 0, 'B': 0, 'C': 0}
    for lead in leads:
        tiers[lead['score']['tier']] += 1
    report += f"\n📈 Pipeline: A={tiers['A']} | B={tiers['B']} | C={tiers['C']} | Seasonal: x{seasonal:.2f}\n\n"

    # Top Architects
    top_arch = sorted(architects, key=lambda a: a.get('score', 0), reverse=True)[:3]
    report += "🤝 Top Architects:\n"
    for arch in top_arch:
        report += f"  • {arch['name']} | Score: {arch.get('score', 0):.1f}\n"

    report += "\n🚀 Action Items:\n"
    report += "  - Call A-leads with top architects\n"
    report += "  - Nurture B-leads quarterly\n"
    report += "  - Review auto-detected candidates\n"
    report += f"  - RJ Market: {'Growing' if seasonal > 1.05 else 'Stable'}\n"

    return report

def api_status_report(config: APIConfig) -> str:
    """Status of API integrations."""
    report = "=== 🔌 API INTEGRATION STATUS ===\n"
    report += f"NewsAPI: {'✅ Active' if config.news_enabled else '⚠️ Add key: newsapi.org'}\n"
    report += f"BrasilAPI: {'✅ Active' if config.brasil_api_enabled else '❌ Disabled'}\n"
    report += f"RSS Bids: {'✅ Active' if config.rss_enabled else '❌ Disabled'}\n"
    report += f"Economic: {'✅ Active' if config.economic_enabled else '❌ Disabled'}\n"
    if os.path.exists(get_cache_path(config, "news_triggers")):
        report += "📦 News cache: Fresh data available\n"
    return report

def export_to_csv(leads: List[Dict], filename: str = "mirage_leads_v2.csv"):
    """Export scored leads to CSV."""
    if not leads:
        return
    keys = ['name', 'industry', 'location', 'employee_count', 'cnpj', 'referral_source', 'score_total', 'tier', 'notes']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for lead in leads:
            row = {k: str(lead.get(k, '') or '') for k in keys}
            row['score_total'] = f"{lead['score']['total']:.1f}"
            row['tier'] = lead['score']['tier']
            row['notes'] = '; '.join(lead['score']['notes'])
            writer.writerow(row)
    print(f"📄 Exported to {filename}")


# =============================================================================
# 🎉 DEMO / MAIN SCRIPT
# =============================================================================
if __name__ == "__main__":
    # Sample data (v1 style)
    sample_leads = [
        {
            'name': 'TechNova RJ',
            'industry': 'tech',
            'employee_count': 300,
            'location': 'Rio de Janeiro',
            'has_recent_trigger': False,
            'notes': [],
            'cnpj': '42.170.255/0001-56'  # Real-ish example
        },
        {
            'name': 'Banco Financeiro',
            'industry': 'finance',
            'employee_count': 750,
            'location': 'Rio de Janeiro',
            'has_recent_trigger': True,
            'notes': ['Manual note'],
            'cnpj': None
        },
        {
            'name': 'LawCorp Advogados',
            'industry': 'legal',
            'employee_count': 80,
            'location': 'Rio de Janeiro',
            'cnpj': '33.000.167/0001-00'
        },
        {
            'name': 'Retail Chain',
            'industry': 'retail',
            'employee_count': 150,
            'location': 'Niterói',
            'has_recent_trigger': False,
            'cnpj': None
        }
    ]

    sample_architects = [
        {'name': 'Arq. Elite RJ', 'past_deals_mirage': 6, 'recent_momentum': 0.9},
        {'name': 'DesignPro', 'past_deals_mirage': 4, 'recent_momentum': 0.85},
        {'name': 'Urban Arch', 'past_deals_mirage': 2, 'recent_momentum': 0.7}
    ]

    # Init
    config = APIConfig()
    leads = load_leads()
    if not leads:
        leads = sample_leads.copy()
    architects = sample_architects.copy()

    print(api_status_report(config))

    print("\n" + "="*70)
    print("🚀 FULLY AUTOMATED v2 MODE (APIs + Scoring)")
    print("="*70)
    leads_auto, arch_auto, _ = run_fully_automated(config, leads, architects)
    print(generate_monthly_report(leads_auto, arch_auto))

    print("\n" + "="*70)
    print("📋 SEMI-AUTOMATED v1 MODE (Scoring Only)")
    print("="*70)
    leads_v1, arch_v1 = run_semi_automated(sample_leads.copy(), sample_architects.copy())
    print(generate_monthly_report(leads_v1, arch_v1))

    # Exports
    export_to_csv(leads_auto)
    save_leads(leads_auto)

    print("\n✅ Ready! Edit config, add NewsAPI key, re-run monthly.")
    print("   Leads persist in leads.json. Cache auto-refreshes.")