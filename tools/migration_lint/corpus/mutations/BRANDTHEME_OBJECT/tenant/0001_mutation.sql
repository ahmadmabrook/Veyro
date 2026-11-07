-- Mutation: a BrandTheme name on a plt01 object. D15.10 keeps BrandTheme single-owner (WHT-01).
ALTER TABLE plt01.brand_appearance ADD COLUMN brand_theme_id uuid;
