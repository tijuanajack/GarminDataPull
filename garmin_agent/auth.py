diff --git a/garmin_agent/auth.py b/garmin_agent/auth.py
index aacfe753436dbe6f53304fb818aede85798c6b18..53adf6ca1ea52b32e54d4406a5ab9d22b433298d 100644
--- a/garmin_agent/auth.py
+++ b/garmin_agent/auth.py
@@ -30,38 +30,39 @@ def _token_cache_mode() -> str:
 
 
 def login(email: str, password: str, mfa: Optional[str] = None) -> Garmin:
     """Authenticate with Garmin using token cache + credential fallback.
 
     Modes:
       - readwrite: try token login; on credential login success, persist tokens.
       - readonly: try token login; credential login allowed but tokens not persisted.
       - off: skip token login and never write token files.
     """
     mode = _token_cache_mode()
     store = _token_store_dir()
     can_read_tokens = mode in {"readwrite", "readonly"}
     can_write_tokens = mode == "readwrite"
 
     if can_read_tokens:
         try:
             g = Garmin()
             g.login(str(store))
             return g
         except Exception as exc:
             if os.getenv("GITHUB_ACTIONS") == "true":
                 raise GarminAuthError(f"Token-based login failed: {exc}") from exc
 
     try:
-        g = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
-        state, session = g.login()
-        if state == "needs_mfa":
+        def prompt_mfa() -> str:
             if not mfa:
                 raise GarminAuthError("MFA required but GARMIN_MFA_CODE was not provided")
-            g.resume_login(session, mfa)
+            return mfa
 
+        g = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)
         if can_write_tokens:
             store.mkdir(parents=True, exist_ok=True)
-            g.garth.dump(str(store))
+            g.login(str(store))
+        else:
+            g.login()
         return g
     except Exception as exc:
         raise GarminAuthError(f"Garmin authentication failed: {exc}") from exc
