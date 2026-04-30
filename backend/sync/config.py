"""
Merchant registry — maps retailer names to Apify Actor IDs and run config.
Add new merchants here; the scrape manager picks them up automatically.
"""

MERCHANT_REGISTRY: dict = {
    "liquorland": {
        "actor_id": "dromb/liquorland-au-catalog-product-lookup-unofficial",
        "max_items": 50,   # per-page cap; actor hard-limits to 50 per call
        "pages": 3,        # try up to 3 pages; stops early if a page is short
        "enabled": True,
        "actor_input": {
            "operation": "category",
            "path": "/wine",
            "state": "sa",
            "show": 50,
            "includeRaw": False,
        },
    },
    "danmurphys": {
        "actor_id": "apify/web-scraper",
        "max_items": 50,
        "enabled": False,
        "actor_input": {
            "startUrls": [
                {"url": "https://www.danmurphys.com.au/catalogue/wine/red-wine"},
                {"url": "https://www.danmurphys.com.au/catalogue/wine/white-wine"},
                {"url": "https://www.danmurphys.com.au/catalogue/wine/sparkling"},
            ],
            "maxCrawlingDepth": 1,
            "pageFunction": """
async function pageFunction(context) {
    const { $, request, log } = context;
    const products = [];
    const seen = new Set();

    // Dan Murphy's product cards — selectors may need tuning after first run
    const selectors = [
        '[data-testid="product-card"]',
        '[class*="ProductCard"]',
        '[class*="product-card"]',
        'article[class*="product"]',
    ];

    let container = null;
    for (const sel of selectors) {
        const found = $(sel);
        if (found.length > 0) { container = found; break; }
    }

    if (!container) {
        log.warning('No product cards found on ' + request.url);
        return products;
    }

    container.each((_, el) => {
        const nameSelectors = ['[class*="name"]','[class*="title"]','h3','h2'];
        const priceSelectors = ['[class*="price"]','[data-testid*="price"]'];
        const linkSelectors  = ['a[href*="/product"]','a[href*="/catalogue"]','a'];

        let name = '';
        for (const s of nameSelectors) {
            name = $(el).find(s).first().text().trim();
            if (name) break;
        }

        let priceRaw = '';
        for (const s of priceSelectors) {
            priceRaw = $(el).find(s).first().text().trim();
            if (priceRaw) break;
        }
        const price = parseFloat(priceRaw.replace(/[^0-9.]/g, ''));

        let href = '';
        for (const s of linkSelectors) {
            href = $(el).find(s).first().attr('href') || '';
            if (href) break;
        }
        const url = href ? new URL(href, 'https://www.danmurphys.com.au').href : null;

        if (!name || isNaN(price) || seen.has(name)) return;
        seen.add(name);
        products.push({ name, price, url, retailer: 'danmurphys' });
    });

    log.info(`Extracted ${products.length} products from ${request.url}`);
    return products;
}
""",
        },
    },
}
