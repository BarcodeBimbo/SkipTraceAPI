# <div align="center">[Patched] SkipGenie API Manager (Quart + Hypercorn)</div>

This project is an asynchronous RESTful API interface to automate interaction with SkipGenie, built using [Quart](https://pgjones.gitlab.io/quart/) and [Hypercorn](https://pgjones.gitlab.io/hypercorn/). It includes user search, creation, editing, and balance-checking capabilities through scraping and session-based interactions.

The primary purpose of this project is to demonstrate how SkipGenie’s legacy authentication system was vulnerable to exploitation specifically, how it could be manipulated to grant unauthorized administrative access.


<div align="center">
  <img src="https://github.com/user-attachments/assets/4a9a9e47-a5b9-434d-b4a9-19e4851b1186" alt="" height="300">
</div>

---

## 🔧 Features

* Full async using `aiohttp` and `Quart`
* Automated login and session reuse for performance
* User scraping, creation, balance checking
* HTML parsing using BeautifulSoup
* Secure API access with `admin_key`
* Data caching in `users_data.json`
* Created users logged in `created_users.log`

---

## 📂 File Structure

```
.
├── SkipTraceAPI.py                # Main application script
├── users_data.json       # Cache of user data
├── created_users.log     # Log of generated users
├── README.md             # Project description
```

---

## 🔐 Admin Key Authentication

All endpoints require `admin_key` in the request:

```
admin_key=b811-9dad-11d1
```

---

## 🚀 Getting Started

### 1. Clone & Install

```bash
git clone https://github.com/yourname/skipgenie-api.git
cd skipgenie-api
pip install -r requirements.txt
```

**`requirements.txt`**

```
quart
aiohttp
beautifulsoup4
hypercorn
```

### 2. Set Admin Credentials

Edit `setup_admin_session()` and `login_session()` to insert your credentials.

---

## 🔎 API Endpoints

### `/v2/search`

**Method:** `GET` or `POST`

**Params:**

* `firstName`, `lastName`, `middle`, `street`, `city`, `state`, `zip`

**Returns:**

```json
{
  "people": {
    "person": [
      {
        "names": [
          {
            "id": 1,
            "Name": "John Doe",
            "Age": "35",
            "Phones": ["(123) 456-7890"],
            ...
          }
        ]
      }
    ]
  }
}
```

---

### `/v2/balance`

**Method:** `GET`

Returns balance info for the account.

```json
{
  "CreditBank": "100",
  "SmartCredits": "50"
}
```

---

### `/v2/user/create`

**Method:** `GET` or `POST`
**Query param:** `role=0` (admin) or `role=1` (user)

Creates and auto-edits a new user, logging to `created_users.log`.

---

### `/v2/user/edit`

**Method:** `GET`
**Params:** `email=<email|username|name>`

Optionally pass fields like:

* `SearchCount`, `SkipAllowance`, `PhoneCredits`, etc.

---

### `/v2/user/balancebyuser`

**Method:** `GET`
**Query:** `user=<username>`

Returns balance for a user found in `created_users.log`.

---

### `/v2/user/finduser`

**Method:** `GET`
**Query:** `user=<username>`

Find user from cached or freshly downloaded `users_data.json`.

---

## 📄 Logging

* **User log:** `created_users.log`
* **User cache:** `users_data.json`

---

## ⚠️ Legal & Usage

This script automates access to SkipGenie’s platform via session scraping. Use only with explicit permission. This may violate their terms of service if used improperly.

---

## 📧 Contact

**Developer:** `Joshua`
**Email:** `legal@tlo.sh`

---

## ▶️ Run Server

```bash
python app.py
```

Listens on:

```
http://127.0.0.1:3000
```

---
