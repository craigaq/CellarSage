-- Null out false-positive critic scores from the initial matching run.
-- These were matched on generic tokens (e.g. "Estate Chardonnay") or
-- varietal mismatches rather than genuine brand alignment.
-- Safe to re-run — WHERE critic_source = 'wine_enthusiast' prevents
-- accidentally touching any future GWS scores.

UPDATE wines
SET    critic_score     = NULL,
       critic_source    = NULL,
       match_confidence = NULL
WHERE  critic_source = 'wine_enthusiast'
  AND  name IN (
    -- Wrong winery: "Taylors" matched to "Stolo / Talley / Tudal Estate"
    'Taylors Estate Chardonnay 750mL',
    'Taylors Estate Chardonnay 750mL Bottle',
    'Taylors Estate Cabernet Sauvignon 750mL',
    'Taylors Estate Cabernet Sauvignon 750mL Bottle',

    -- Wrong winery: "Wynns" matched to "Turnbull / Spin the Bottle"
    'Wynns Black Label Cabernet Sauvignon 750mL',
    'Wynns The Siding Cabernet Sauvignon 750mL Bottle',

    -- Wrong winery: "Pepperjack" matched to "Jack"
    'Pepperjack Cabernet Sauvignon 750mL',

    -- Variety mismatch: Sauvignon Blanc matched to Cabernet Sauvignon
    'Jacob''s Creek Sauvignon Blanc 750mL',

    -- Style mismatch: Shiraz Rosé matched to red Reserve Shiraz
    'Jacob''s Creek Shiraz Rose 750mL',

    -- Blend mismatch: Chardonnay Pinot Noir matched to single-variety Chardonnay
    'Jacob''s Creek Reserve Chardonnay Pinot Noir 750mL',

    -- Wrong winery: "Sisters Run" matched to "Four Sisters"
    'Sisters Run Shiraz 750mL',
    'Sisters Run Cabernet Sauvignon 750mL',

    -- Wrong winery: "St Hugo" matched to "Tom Gore"
    'St Hugo Cabernet Sauvignon 750mL',

    -- Wrong winery: "Red Hill" matched to "Russian Hill"
    'Red Hill Estate Pinot Noir 750mL',

    -- Wrong winery: "Zema" matched to "Sula"
    'Zema Estate Shiraz 750mL Bottle',

    -- Wrong winery: "Portone" matched to "Zorzon"
    'Portone Pinot Grigio 750mL',

    -- Wrong winery: "Lambrook" matched to "Cottesbrook"
    'Lambrook Sauvignon Blanc 750mL Bottle',

    -- Wrong winery: "Cradle Bay" matched to "Caroline Bay"
    'Cradle Bay Sauvignon Blanc 750mL',

    -- Wrong winery: "Serafino / The Y Series / Johnny Q" matched to generic Cab Sauv
    'Serafino Cabernet Sauvignon 750mL Bottle',
    'The Y Series Cabernet Sauvignon 750mL Bottle',
    'Johnny Q Cabernet Sauvignon 750mL',

    -- Wrong label: "Red Label" matched to "White Label" (different product)
    'Wolf Blass Red Label Chardonnay 750mL',

    -- Bin number mismatch: Bin 28 matched to Bin 128 (different wine)
    'Penfolds Bin 28 Shiraz (CLR) 750mL'
);

-- Verify: show how many rows were cleared
SELECT COUNT(*) AS false_positives_cleared
FROM   wines
WHERE  critic_score IS NULL
  AND  name IN (
    'Taylors Estate Chardonnay 750mL',
    'Taylors Estate Chardonnay 750mL Bottle',
    'Taylors Estate Cabernet Sauvignon 750mL',
    'Taylors Estate Cabernet Sauvignon 750mL Bottle',
    'Wynns Black Label Cabernet Sauvignon 750mL',
    'Wynns The Siding Cabernet Sauvignon 750mL Bottle',
    'Pepperjack Cabernet Sauvignon 750mL',
    'Jacob''s Creek Sauvignon Blanc 750mL',
    'Jacob''s Creek Shiraz Rose 750mL',
    'Jacob''s Creek Reserve Chardonnay Pinot Noir 750mL',
    'Sisters Run Shiraz 750mL',
    'Sisters Run Cabernet Sauvignon 750mL',
    'St Hugo Cabernet Sauvignon 750mL',
    'Red Hill Estate Pinot Noir 750mL',
    'Zema Estate Shiraz 750mL Bottle',
    'Portone Pinot Grigio 750mL',
    'Lambrook Sauvignon Blanc 750mL Bottle',
    'Cradle Bay Sauvignon Blanc 750mL',
    'Serafino Cabernet Sauvignon 750mL Bottle',
    'The Y Series Cabernet Sauvignon 750mL Bottle',
    'Johnny Q Cabernet Sauvignon 750mL',
    'Wolf Blass Red Label Chardonnay 750mL',
    'Penfolds Bin 28 Shiraz (CLR) 750mL'
);
