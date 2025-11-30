INSERT INTO barbour_color_map (
    color_code,
    raw_name,
    norm_key,
    source,
    is_confirmed
)
VALUES
    -- ===== Basic solid colors =====
    ('BK', 'black', 'black', 'config_code_map', TRUE),
    ('NY', 'navy', 'navy', 'config_code_map', TRUE),
    ('OL', 'olive', 'olive', 'config_code_map', TRUE),
    ('WH', 'white', 'white', 'config_code_map', TRUE),
    ('GN', 'green', 'green', 'config_code_map', TRUE),
    ('GY', 'grey', 'grey', 'config_code_map', TRUE),
    ('BR', 'brown', 'brown', 'config_code_map', TRUE),
    ('BE', 'beige', 'beige', 'config_code_map', TRUE),
    ('SG', 'sage', 'sage', 'config_code_map', TRUE),
    ('ST', 'stone', 'stone', 'config_code_map', TRUE),
    ('BL', 'blue', 'blue', 'config_code_map', TRUE),
    ('RE', 'red', 'red', 'config_code_map', TRUE),
    ('PI', 'pink', 'pink', 'config_code_map', TRUE),
    ('CR', 'cream', 'cream', 'config_code_map', TRUE),
    ('CH', 'charcoal', 'charcoal', 'config_code_map', TRUE),
    ('TN', 'tan', 'tan', 'config_code_map', TRUE),
    ('KH', 'khaki', 'khaki', 'config_code_map', TRUE),
    ('YE', 'yellow', 'yellow', 'config_code_map', TRUE),
    ('OR', 'orange', 'orange', 'config_code_map', TRUE),
    ('PU', 'purple', 'purple', 'config_code_map', TRUE),
    ('IN', 'indigo', 'indigo', 'config_code_map', TRUE),
    ('TA', 'taupe', 'taupe', 'config_code_map', TRUE),
    ('CM', 'camel', 'camel', 'config_code_map', TRUE),
    ('TE', 'teal', 'teal', 'config_code_map', TRUE),
    ('CO', 'cobalt', 'cobalt', 'config_code_map', TRUE),
    ('AQ', 'aqua', 'aqua', 'config_code_map', TRUE),
    ('BU', 'burgundy', 'burgundy', 'config_code_map', TRUE),
    ('RU', 'rustic', 'rustic', 'config_code_map', TRUE),
    ('SN', 'sand', 'sand', 'config_code_map', TRUE),

    -- ===== Confirmed special / Barbour-specific =====
    ('PI', 'Arabesque', 'arabesque', 'config_code_map', TRUE),
    ('BR', 'Bark', 'bark', 'config_code_map', TRUE),
    ('RE', 'Bordeaux', 'bordeaux', 'config_code_map', TRUE),
    ('ST', 'Clay', 'clay', 'config_code_map', TRUE),
    ('WH', 'Cloud', 'cloud', 'config_code_map', TRUE),
    ('OL', 'Fern', 'fern', 'config_code_map', TRUE),
    ('GN', 'Forest', 'forest', 'config_code_map', TRUE),
    ('TN', 'Midnight', 'midnight', 'config_code_map', TRUE),
    ('BE', 'Mist', 'mist', 'config_code_map', TRUE),
    ('CR', 'Pearl', 'pearl', 'config_code_map', TRUE),

    -- ===== Multi-tone / Tartan derived =====
    ('SN', 'Beech/Classic', 'beech_classic', 'config_code_map', TRUE),
    ('BR', 'Black Oak', 'black_oak', 'config_code_map', TRUE),
    ('GN', 'Dundee Tartan', 'dundee_tartan', 'config_code_map', TRUE),
    ('BK', 'Black Carbon', 'black_carbon', 'config_code_map', TRUE),
    ('BR', 'Umber', 'umber', 'config_code_map', TRUE),

    ('ST', 'Light Fawn', 'light_fawn', 'config_code_map', TRUE),
    ('CR', 'Pearl/Navy', 'pearl_navy', 'config_code_map', TRUE),
    ('BE', 'Trench', 'trench', 'config_code_map', TRUE),
    ('NY', 'Navy/Classic', 'navy_classic', 'config_code_map', TRUE),

    ('OL', 'Deep Olive/Ancient Tartan', 'deep_olive_ancient_tartan', 'config_code_map', TRUE),
    ('BL', 'Sky Micro Check', 'sky_micro_check', 'config_code_map', TRUE),

    ('OL', 'Fern/Classic Tartan', 'fern_classic_tartan', 'config_code_map', TRUE),
    ('BR', 'Bark/Muted', 'bark_muted', 'config_code_map', TRUE),

    ('TA', 'Tan/Dress Tartan', 'tan_dress_tartan', 'config_code_map', TRUE),
    ('NY', 'Royal Navy/Dress Tartan', 'royal_navy_dress_tartan', 'config_code_map', TRUE),

    ('OL', 'Fern/Ancient Tartan', 'fern_ancient_tartan', 'config_code_map', TRUE),
    ('OL', 'Archive Olive/Ancient Tartan', 'archive_olive_ancient_tartan', 'config_code_map', TRUE),
    ('RU', 'Rustic/Ancient Tartan', 'rustic_ancient_tartan', 'config_code_map', TRUE),
    ('OL', 'Fern/Beech/Ancient Tartan', 'fern_beech_ancient_tartan', 'config_code_map', TRUE),
    ('OL', 'Fern/Sage/Ancient Tartan', 'fern_sage_ancient_tartan', 'config_code_map', TRUE)

ON CONFLICT (color_code, raw_name) DO UPDATE
SET
    norm_key     = EXCLUDED.norm_key,
    source       = EXCLUDED.source,
    is_confirmed = EXCLUDED.is_confirmed;
