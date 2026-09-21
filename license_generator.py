import sys
import os

# Add desktop_app to path to import licensing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_app"))
import licensing

def main():
    print("=" * 60)
    print("   AI LASER SCANNER - ADMIN LICENSE GENERATOR")
    print("=" * 60)
    
    current_hwid = licensing.get_machine_id()
    print(f"\n[i] আপনার বর্তমান পিসির Machine ID (HWID): {current_hwid}")
    
    target_hwid = input(f"\nক্লায়েন্টের Machine ID লিখুন (Enter চাপলে '{current_hwid}' ব্যবহৃত হবে, অথবা 'UNIVERSAL' লিখুন): ").strip()
    if not target_hwid:
        target_hwid = current_hwid
        
    print("\nমেয়াদ (Duration) নির্বাচন করুন:")
    print("  1. ৩০ দিন (1 Month)")
    print("  2. ৯০ দিন (3 Months)")
    print("  3. ১৮০ দিন (6 Months)")
    print("  4. ৩৬৫ দিন (1 Year)")
    print("  5. আজীবন / আনলিমিটেড (Lifetime)")
    
    choice = input("পছন্দ নির্বাচন করুন (1-5, ডিফল্ট 5): ").strip()
    days_map = {"1": 30, "2": 90, "3": 180, "4": 365, "5": 0}
    days = days_map.get(choice, 0)
    
    key = licensing.generate_license_key(target_hwid, days)
    
    print("\n" + "=" * 60)
    print("🎉 তৈরি হওয়া লাইসেন্স কি (License Key):")
    print("-" * 60)
    print(f"  {key}")
    print("-" * 60)
    print(f"  টার্গেট HWID: {target_hwid.upper()}")
    print(f"  মেয়াদ: {'আজীবন (Lifetime)' if days == 0 else f'{days} দিন'}")
    print("=" * 60)
    
    # Check if user wants to auto-activate this PC
    if target_hwid.upper() in [current_hwid.upper(), "UNIVERSAL"]:
        act = input("\nআপনি কি আপনার বর্তমান পিসির অ্যাপটি এখনই এই কি দিয়ে অ্যাক্টিভেট করতে চান? (y/n): ").strip().lower()
        if act == 'y':
            # Save to desktop_offline_app
            offline_lic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_offline_app", "license.lic")
            with open(offline_lic, "w", encoding="utf-8") as f:
                f.write(key.strip())
            # Save to desktop_app if directory exists
            desktop_app_lic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_app", "license.lic")
            if os.path.exists(os.path.dirname(desktop_app_lic)):
                with open(desktop_app_lic, "w", encoding="utf-8") as f:
                    f.write(key.strip())
            # Save to root directory (where compiled .exe might run)
            root_lic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "license.lic")
            with open(root_lic, "w", encoding="utf-8") as f:
                f.write(key.strip())
            print("✅ আপনার বর্তমান পিসিতে লাইসেন্স অ্যাক্টিভেট করা হয়েছে!")

if __name__ == "__main__":
    main()
