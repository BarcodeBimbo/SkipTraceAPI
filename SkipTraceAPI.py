import hypercorn.asyncio, json, os, string, random, aiohttp, asyncio

from quart import Quart, request, jsonify, Response
from bs4 import BeautifulSoup
from collections import OrderedDict
from datetime import datetime, timedelta
from hypercorn.config import Config
from functools import wraps

app = Quart(__name__)

def require_admin_key(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if request.method == "GET":
            data = request.args
        else:
            data = await request.get_json()
            if data is None:
                data = {}

        admin_key = data.get("admin_key")
        if admin_key != "b811-9dad-11d1":
            return jsonify({"error": "Invalid or missing admin key."}), 403

        return await func(*args, **kwargs)
    return wrapper

# -------------------------------
# Session Login Helper (async)
# -------------------------------
async def login_session(email, password):
    session = aiohttp.ClientSession()
    login_url = "https://app.skipgenie.com/Account/Login?ReturnUrl=%2F"
    async with session.get(login_url) as response:
        text = await response.text()
    soup = BeautifulSoup(text, "html.parser")
    token = soup.find("input", {"name": "__RequestVerificationToken"})["value"]
    login_data = {
        "__RequestVerificationToken": token,
        "Email": email,
        "Password": password,
        "RememberMe": "false"
    }
    await session.post(login_url, data=login_data)
    return session

# -------------------------------
# Global Admin Session
# -------------------------------
admin_session = None

async def setup_admin_session():
    global admin_session
    admin_session = await login_session("", "")

async def load_users_file():
    if not os.path.exists("users_data.json"):
        return []

    with open("users_data.json", "r") as f:
        users_root = json.load(f)

    # ✅ users are inside "data"
    return users_root.get("data", [])

async def download_users_file():
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://app.skipgenie.com/User",
        "Accept": "application/json, text/javascript, */*; q=0.01"
    }
    async with admin_session.get("https://app.skipgenie.com/User/getUsers?requestJson=All", headers=headers) as response:
        users_root = await response.json()

    # Save to local file
    with open("users_data.json", "w") as f:
        json.dump(users_root, f, indent=4)

async def load_users_file():
    if not os.path.exists("users_data.json"):
        return []

    with open("users_data.json", "r") as f:
        users_root = json.load(f)

    if isinstance(users_root, dict) and "data" in users_root:
        return users_root["data"]
    else:
        return []

async def balance_for_created_users(username):
    try:
        if not os.path.exists("created_users.log"):
            return {"error": "Log file not found."}

        with open("created_users.log", "r") as f:
            lines = f.readlines()

        for line in lines:
            try:
                parts = line.split("|")
                email = parts[0].split("user:")[1].strip()
                password = parts[1].strip()

                # Only match if username matches
                if username.lower() in line.lower() or username.lower() in email.lower():
                    session = await login_session(email, password)
                    async with session.get("https://app.skipgenie.com/Home/Index") as page:
                        soup = BeautifulSoup(await page.text(), "html.parser")

                    credit_bank = "Not found"
                    smart_credits = "Not found"

                    for li in soup.find_all("li"):
                        if "Credit Bank:" in li.text:
                            credit_bank = li.text.split(":")[-1].strip().replace(" ", "")
                    span = soup.find("span", id="SmartCredits")
                    if span:
                        smart_credits = span.text.strip()

                    await session.close()

                    return {
                        "email": email,
                        "CreditBank": credit_bank,
                        "SmartCredits": smart_credits
                    }

            except Exception as e:
                print(f"[ERROR] Processing {line}: {e}")

        return {"error": "User not found."}

    except Exception as e:
        return {"error": str(e)}


# -------------------------------
# HTML Parser (parse people results)
# -------------------------------
def parse_people_html(html):
    soup = BeautifulSoup(html, "html.parser")
    people = []

    panels = soup.find_all("div", class_=lambda x: x and "panel" in x and ("panel-success" in x or "panel-warning" in x))
    for index, panel in enumerate(panels, start=1):
        person = {
            "id": index,
            "Name": "",
            "Age": "",
            "AddressHistory": [],
            "Phones": [],
            "Relatives": [],
            "Associates": [],
            "Emails": [],
            "Filings": []
        }

        heading = panel.find("div", class_="panel-heading")
        if heading:
            text = heading.get_text(separator=" ", strip=True)
            try:
                if " : " in text:
                    after_colon = text.split(" : ")[-1]
                    name_age_part = after_colon.split(" - ")[0].strip()
                    *name_parts, age = name_age_part.rsplit(" ", 1)
                    if age.isdigit():
                        person["Age"] = age
                        person["Name"] = " ".join(name_parts).title()
            except Exception as err:
                print("[WARN] Failed to parse name/age:", err)

        address_section = panel.find("div", id=lambda x: x and "AddressHistoryDiv_" in x)
        if address_section:
            addresses = address_section.find_all_next("a")
            for address in addresses:
                addr_text = address.get_text(strip=True)
                dates_tag = address.find_next_sibling(string=True)
                if dates_tag and "to" in dates_tag:
                    person["AddressHistory"].append({
                        "address": addr_text,
                        "dates": dates_tag.strip()
                    })

        phone_section = panel.find("div", id="phoneSearch")
        if phone_section:
            spans = phone_section.find_all("span")
            for span in spans:
                phone = span.get_text(strip=True)
                if phone.startswith("(") and ")" in phone:
                    person["Phones"].append(phone)

        email_spans = panel.find_all("span", id=lambda x: x and x.startswith(f"email_{index}_"))
        for span in email_spans:
            email = span.get_text(strip=True)
            if "@" in email:
                person["Emails"].append(email)

        relative_div = panel.find("div", id="RelativeDiv")
        if relative_div:
            links = relative_div.find_all_next("a")
            for link in links:
                if "/Search/Search/RT_" in link.get("href", ""):
                    person["Relatives"].append(link.get_text(strip=True))

        associate_div = panel.find("div", id="AssociateDiv")
        if associate_div:
            links = associate_div.find_all_next("a")
            for link in links:
                if "/Search/Search/RT_" in link.get("href", ""):
                    person["Associates"].append(link.get_text(strip=True))

        indicator_div = panel.find("div", class_="col-md-2")
        if indicator_div:
            indicators = indicator_div.find_all("span")
            person["Filings"] = [i.get_text(strip=True) for i in indicators if i.get_text(strip=True)]

        people.append(person)

    return people

# -------------------------------
# /v2/search
# -------------------------------
@app.route("/v2/search", methods=["GET", "POST"])
@require_admin_key
async def search():
    try:
        data = request.args if request.method == "GET" else await request.get_json()
        street = data.get("street", "")
        city = data.get("city", "")
        state = data.get("state", "")
        zip_code = data.get("zip", "")
        first = data.get("firstName", "")
        middle = data.get("Middle", "")
        last = data.get("lastName", "")

        if not any([first, last, street, city, state, zip_code]):
            return jsonify({"error": "At least one valid search field must be provided."}), 400

        session = await login_session("", "")
        search_url = "https://app.skipgenie.com/Search/Search"

        async with session.get(search_url) as search_page:
            soup = BeautifulSoup(await search_page.text(), "html.parser")
            token = soup.find("input", {"name": "__RequestVerificationToken"})["value"]

        search_data = {
            "__RequestVerificationToken": token,
            "lastName": last,
            "firstName": first,
            "middleName": middle,
            "street": street,
            "city": city,
            "state": state,
            "zip": zip_code,
            "donothing": ""
        }

        async with session.post(search_url, data=search_data) as response:
            html = await response.text()

        people_raw = parse_people_html(html)

        ordered_results = []
        for person in people_raw:
            ordered_person = OrderedDict()
            ordered_person["id"] = person.get("id")
            ordered_person["Name"] = person.get("Name")
            ordered_person["Age"] = person.get("Age")
            ordered_person["AddressHistory"] = person.get("AddressHistory", [])
            ordered_person["Phones"] = person.get("Phones", [])
            ordered_person["Relatives"] = person.get("Relatives", [])
            ordered_person["Associates"] = person.get("Associates", [])
            ordered_person["Emails"] = person.get("Emails", [])
            ordered_person["Filings"] = person.get("Filings", [])
            ordered_results.append(ordered_person)

        await session.close()

        return Response(json.dumps({"people":{"person":[{"names": ordered_results}]}}, indent=4), mimetype="application/json")

    except Exception as e:
        print("[ERROR]", str(e))
        return jsonify({"error": str(e)}), 500


 # -------------------------------
# /v2/user/balancebyusername
# -------------------------------
@app.route("/v2/user/balancebyuser", methods=["GET"])
@require_admin_key
async def balance_by_user():
    username = request.args.get("user", "").strip()

    if not username:
        return jsonify({"error": "Missing username."}), 400

    balance = await balance_for_created_users(username)

    return jsonify(balance)
    
# -------------------------------
# /v2/balance
# -------------------------------
@app.route("/v2/balance", methods=["GET"])
@require_admin_key
async def get_balance():
    try:
        session = await login_session("", "")
        async with session.get("https://app.skipgenie.com/Home/Index") as page:
            soup = BeautifulSoup(await page.text(), "html.parser")

        credit_bank = "Not found"
        smart_credits = "Not found"

        for li in soup.find_all("li"):
            if "Credit Bank:" in li.text:
                credit_bank = li.text.split(":")[-1].strip().replace(" ", "")
        span = soup.find("span", id="SmartCredits")
        if span:
            smart_credits = span.text.strip()

        await session.close()

        return jsonify({
            "CreditBank": credit_bank,
            "SmartCredits": smart_credits
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------
# /v2/user/edit
# -------------------------------
@app.route("/v2/user/edit", methods=["GET"])
@require_admin_key
async def user_edit():
    data = request.args
    identifier = data.get("email")  # still getting 'email' param, but now used as identifier

    if not identifier:
        return jsonify({"error": "Missing identifier (email/username/name)"}), 400

    try:
        # Step 1: Refresh users file
        if os.path.exists("users_data.json"):
            os.remove("users_data.json")
        await download_users_file()

        # Step 2: Load users
        users_list = await load_users_file()

        identifier = identifier.strip().lower()

        # Step 3: Try to match by Email, Username, or Name
        user = next(
            (u for u in users_list if
             u.get("Email", "").strip().lower() == identifier or
             u.get("UserName", "").strip().lower() == identifier or
             u.get("Name", "").strip().lower() == identifier),
            None
        )

        if not user:
            return jsonify({"error": "User with that email/username/name not found."}), 404

        user_id = user.get("userID")

        # Step 4: Proceed to edit the user
        session = await login_session("", "")
        edit_url = f"https://app.skipgenie.com/User/Edit/{user_id}"

        async with session.get(edit_url) as page:
            soup = BeautifulSoup(await page.text(), "html.parser")
            token = soup.find("input", {"name": "__RequestVerificationToken"})["value"]

        form_data = {
            "__RequestVerificationToken": token,
            "id": user_id,
            "Email": user.get("Email"),
            "Password": "",
            "ConfirmPassword": "",
            "PricePerSearch": int(data.get("PricePerSearch", user.get("PricePerSearch", 0))),
            "ReturnMailPrice": int(data.get("ReturnMailPrice", user.get("ReturnMailPrice", 0))),
            "MonthlyPayment": int(data.get("MonthlyPayment", user.get("MonthlyPayment", 0))),
            "PhoneNumber": user.get("PhoneNumber", ""),
            "UserName": user.get("UserName", ""),
            "Address": user.get("Address", ""),
            "City": user.get("City", ""),
            "State": user.get("State", ""),
            "Zip": user.get("Zip", ""),
            "Role": user.get("Role", "User"),
            "Active": "active",
            "Plan": user.get("Plan", "SGOne"),
            "Unlimited": "true",
            "BillingCycle": user.get("PlanRenewal", datetime.now().strftime("%m/%d/%Y")),
            "SearchCount": int(data.get("SearchCount", user.get("SearchCount", 10000))),
            "SkipAllowance": int(data["SkipAllowance"]) if "SkipAllowance" in data and data["SkipAllowance"].isdigit() else int(user.get("SkipAllowance", 10000)),
            "PhoneCredits": int(data["PhoneCredits"]) if "PhoneCredits" in data and data["PhoneCredits"].isdigit() else int(user.get("PhoneCredits", 10000)),
            "HowDidYouHearAboutText": user.get("HowDidYouHearAboutText", "")
        }

        headers = {
            "Referer": edit_url,
            "Origin": "https://app.skipgenie.com",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        async with session.post(edit_url, data=form_data, headers=headers) as response:
            result = await response.text()

        await session.close()

        return jsonify({
            "status": response.status,
            "response": "User edited successfully" if response.status == 200 else result,
            "edited_user": {
                "email": user.get("Email"),
                "userID": user.get("userID"),
                "userName": user.get("UserName"),
                "phone": user.get("PhoneNumber"),
                "plan": user.get("Plan"),
                "role": user.get("Role")
            }
        })

    except Exception as e:
        print("[ERROR]", str(e))
        return jsonify({"error": str(e)}), 500


# -------------------------------
# /v2/user/create
# -------------------------------
@app.route("/v2/user/create", methods=["GET", "POST"])
@require_admin_key
async def create_user():
    try:
        # get role param
        role_param = request.args.get("role", "0")
        selected_role = "Administrator" if role_param == "0" else "User"
        plan_selected = "SGOne"

        # generate billing cycle date 15 years from now
        future_date = datetime.now() + timedelta(days=365*15)
        billing_cycle = future_date.strftime("%m/%d/%Y")

        async with admin_session.get("https://app.skipgenie.com/User/Create") as response:
            text = await response.text()
        soup = BeautifulSoup(text, "html.parser")
        token = soup.find("input", {"name": "__RequestVerificationToken"})["value"]

        random_email = f"{''.join(random.choices(string.ascii_lowercase, k=8))}@kevingant.info"
        random_password = ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=12))
        random_name = ''.join(random.choices(string.ascii_letters, k=7)).title()
        random_phone = ''.join(random.choices(string.digits, k=10))
        random_address = f"{random.randint(1, 9999)} Random St"
        random_city = "New York"
        random_state = "NY"
        random_zip = "10001"

        form_data = {
            "__RequestVerificationToken": token,
            "Email": random_email,
            "Password": random_password,
            "ConfirmPassword": random_password,
            "PhoneNumber": random_phone,
            "UserName": random_name,
            "Address": random_address,
            "City": random_city,
            "State": random_state,
            "Zip": random_zip,
            "Role": selected_role,
            "Active": "active",
            "Plan": plan_selected,
            "BillingCycle": billing_cycle,
            "SearchCount": 0
        }

        headers = {
            "Referer": "https://app.skipgenie.com/User/Create",
            "Origin": "https://app.skipgenie.com",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        await admin_session.post("https://app.skipgenie.com/User/Create", data=form_data, headers=headers)

        await asyncio.sleep(10)

        if os.path.exists("users_data.json"):
            os.remove("users_data.json")
        await download_users_file()

        users_list = await load_users_file()

        user_id = "Not found"
        user_info = None
        for user in users_list:
            if user.get("Email", "").lower() == random_email.lower():
                user_id = user.get("userID", "No userID found")
                user_info = user
                break

        # Now edit the user immediately
        edit_url = f"https://app.skipgenie.com/User/Edit/{user_id}"

        async with admin_session.get(edit_url) as page:
            soup = BeautifulSoup(await page.text(), "html.parser")
            edit_token = soup.find("input", {"name": "__RequestVerificationToken"})["value"]

        edit_form_data = {
            "__RequestVerificationToken": edit_token,
            "id": user_id,
            "Email": random_email,
            "Password": random_password,
            "ConfirmPassword": random_password,
            "PricePerSearch": 0,
            "ReturnMailPrice": 0,
            "MonthlyPayment": 0,
            "PhoneNumber": random_phone,
            "UserName": random_name,
            "Address": random_address,
            "City": random_city,
            "State": random_state,
            "Zip": random_zip,
            "Role": selected_role,
            "Active": "active",
            "Plan": plan_selected,
            "Unlimited": "true",
            "BillingCycle": billing_cycle,
            "SearchCount": 10000,
            "SkipAllowance": 10000,
            "PhoneCredits": 10000,
            "HowDidYouHearAboutText": ""
        }

        edit_headers = {
            "Referer": edit_url,
            "Origin": "https://app.skipgenie.com",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        await admin_session.post(edit_url, data=edit_form_data, headers=edit_headers)

        with open("created_users.log", "a") as log_file:
            log_file.write(f"[{datetime.now()}] Created & Edited user: {random_email} | {random_password} | {random_name} | {random_phone} | userID: {user_id}\n")

        return jsonify({
            "email": user_info.get("Email"),
            "password": random_password,
            "userID": user_info.get("userID"),
            "phone": user_info.get("PhoneNumber"),
            "userName": user_info.get("UserName"),
            "plan": user_info.get("Plan"),
            "role": user_info.get("Role"),
            "planRenewal": user_info.get("PlanRenewal"),
            "searchCount": user_info.get("SearchCount"),
            "response": "User created and edited successfully"
        })

    except Exception as e:
        print("[ERROR]", str(e))
        return jsonify({"error": str(e)}), 500

# -------------------------------
# /v2/user/getusers
# -------------------------------

@app.route("/v2/user/finduser", methods=["GET"])
@require_admin_key
async def find_user_by_username():
    try:
        username = request.args.get("user", "").strip().lower()
        if not username:
            return jsonify({"error": "Username parameter is required."}), 400

        # Step 1: Load users from local file
        users_list = await load_users_file()
        username_lookup = {user.get("UserName", "").strip().lower(): user for user in users_list}

        if username in username_lookup:
            found_user = username_lookup[username]
            return jsonify({
                "email": found_user.get("Email"),
                "userID": found_user.get("userID"),
                "phone": found_user.get("PhoneNumber"),
                "userName": found_user.get("UserName"),
                "plan": found_user.get("Plan"),
                "role": found_user.get("Role"),
                "planRenewal": found_user.get("PlanRenewal"),
                "searchCount": found_user.get("SearchCount")
            })

        # Step 2: Not found locally? Refresh users
        if os.path.exists("users_data.json"):
            os.remove("users_data.json")
        
        await download_users_file()

        # Step 3: Load again
        users_list = await load_users_file()
        username_lookup = {user.get("UserName", "").strip().lower(): user for user in users_list}

        if username in username_lookup:
            found_user = username_lookup[username]
            return jsonify({
                "email": found_user.get("Email"),
                "userID": found_user.get("userID"),
                "phone": found_user.get("PhoneNumber"),
                "userName": found_user.get("UserName"),
                "plan": found_user.get("Plan"),
                "role": found_user.get("Role"),
                "planRenewal": found_user.get("PlanRenewal"),
                "searchCount": found_user.get("SearchCount")
            })

        return jsonify({"error": "User not found."}), 404

    except Exception as e:
        print("[ERROR]", str(e))
        return jsonify({"error": str(e)}), 500
# -------------------------------
# Before Server Start
# -------------------------------
@app.before_serving
async def startup():
    await setup_admin_session()

# -------------------------------
# Run the App
# -------------------------------
if __name__ == "__main__":
    config = Config()
    config.bind = ["127.0.0.1:3000"]  # <- Listening on localhost:3000
    asyncio.run(hypercorn.asyncio.serve(app, config))
