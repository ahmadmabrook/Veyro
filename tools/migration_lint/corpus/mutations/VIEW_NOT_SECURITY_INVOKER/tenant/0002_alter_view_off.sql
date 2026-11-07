-- Same violation reached by reversing the setting after creation.
ALTER VIEW plt01.active_brand_count SET (security_invoker = false);
