from garminconnect import Garmin
client = Garmin(email="your@email.com", password="your_password", is_cn=False, return_on_mfa=True)
result1, result2 = client.login()
if result1 == "needs_mfa":
    mfa_code = input("Enter MFA code: ")
    client.resume_login(result2, mfa_code)
client.garth.dump(".garminconnect")
print("✅ Token saved to .garminconnect/")
