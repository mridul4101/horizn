# Instagram Setup Guide

This guide walks you through every step needed to connect your Instagram account to Horizn so it can publish carousels on your behalf.

---

## 1. Convert to a Creator or Business Account

1. Open the **Instagram** app on your phone.
2. Go to **Settings & Privacy → Account type and tools**.
3. Tap **Switch to Professional Account** and choose **Creator** (for personal brands) or **Business** (for companies).
4. Follow the on-screen prompts. You will be asked to select a category.

---

## 2. Connect a Facebook Page (Required by Meta Graph API)

Meta's Graph API requires that your Instagram Creator or Business account is linked to a **Facebook Page**. You do not need to use or post to this Facebook Page—it simply acts as an administrative anchor for Meta's API permissions.

You can do this either from your **Instagram phone app** (fastest) or on a **computer browser**:

### Option A: From the Instagram App on Your Phone (Fastest - ~1 minute)

1. Open **Instagram** and go to your **Profile**.
2. Tap the **Edit profile** button below your bio.
3. Scroll down to the **Public business information** section.
4. Tap on **Page** (it will say *"Connect or create"*).
5. Choose **Connect existing Page** OR **Create Facebook Page**:
   - If you already have a personal Facebook account, log in when prompted.
   - If you don't have a Facebook Page yet, tap **Create Facebook Page**, enter a title (e.g., `Your Name Photos`), choose a category (e.g., `Photographer`), and tap **Done**.
   - Instagram will automatically link to your Facebook account and create/pair the Page in the background.
6. Verify: Once completed, your Page name will appear under **Public business information → Page** in your Edit Profile screen.

---

### Option B: From Your Computer Browser (facebook.com)

If you prefer doing it from your laptop or desktop:

1. **Create a Facebook Page:**
   - Log into Facebook on your browser and visit **[facebook.com/pages/create](https://facebook.com/pages/create)**.
   - Enter a Page name (e.g. `My Landscape Studio`) and category (e.g. `Photographer`).
   - Click **Create Page**.
2. **Link Your Instagram Account:**
   - In the left sidebar of your new Page, click **Settings**.
   - Click **Linked Accounts** (in the left menu).
   - Click **Instagram**, then click the blue **Connect Account** button.
   - A login window will appear. Enter your Instagram Creator account username and password.
   - Click **Confirm**.
3. Your Instagram Creator account is now paired with your Facebook Page.

---

## 3. Create a Meta Developer App

1. Visit [developers.facebook.com](https://developers.facebook.com) and log in with the **same Facebook account** that owns the Page above.
2. Click **My Apps → Create App**.
3. Choose **Other** as the use-case, then **Business** as the app type.
4. Fill in the app name (e.g., `Horizn Local`) and your contact email.
5. Click **Create App**.

---

## 4. Add the Instagram Product and Set Permissions

1. In your new app's dashboard, click **Add Product** and choose **Instagram**.
2. Under **Instagram → API Setup with Instagram Business Login**, click **Set Up**.
3. In the **Permissions** section, add and request the following:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_read_engagement`
4. Under **Valid OAuth Redirect URIs**, add `https://localhost` (used only during token exchange).
5. Save changes.

> **Note:** For testing purposes your app starts in **Development mode**, which limits access to your own account. That is all Horizn needs.

---

## 5. Run the Instagram Business Login OAuth Flow (Short-Lived Token)

1. Construct the authorisation URL (replace `{APP_ID}`):

   ```
   https://www.facebook.com/dialog/oauth
     ?client_id={APP_ID}
     &redirect_uri=https://localhost
     &scope=instagram_basic,instagram_content_publish,pages_read_engagement
     &response_type=code
   ```

2. Open the URL in a browser, log in, and grant the permissions.
3. After approval, Facebook redirects to `https://localhost?code=AQD…`. Copy the `code` value from the URL bar (ignore any browser error about the page failing to load — that is normal).
4. Exchange the code for a **short-lived token** (valid for 1 hour):

   ```bash
   curl "https://graph.facebook.com/v21.0/oauth/access_token" \
     -d "client_id={APP_ID}" \
     -d "client_secret={APP_SECRET}" \
     -d "redirect_uri=https://localhost" \
     -d "code={CODE}"
   ```

   The response contains `{"access_token": "EAA…", "token_type": "bearer"}`.

---

## 6. Exchange for a Long-Lived Token (60 days)

```bash
curl "https://graph.facebook.com/v21.0/oauth/access_token" \
  -d "grant_type=fb_exchange_token" \
  -d "client_id={APP_ID}" \
  -d "client_secret={APP_SECRET}" \
  -d "fb_exchange_token={SHORT_LIVED_TOKEN}"
```

The response contains your **long-lived token** (`expires_in` ≈ 5 183 944 seconds ≈ 60 days).

---

## 7. Find Your Instagram User ID

```bash
curl "https://graph.facebook.com/v21.0/me?fields=id,username&access_token={LONG_LIVED_TOKEN}"
```

Note the returned `id` — this is your **IG_USER_ID**.

---

## 8. Configure `.env`

Open `.env` in the project root and fill in:

```dotenv
META_APP_ID=<your App ID from step 3>
META_APP_SECRET=<your App Secret from step 3>
IG_USER_ID=<id from step 7>
IG_ACCESS_TOKEN=<long-lived token from step 6>
```

---

## 9. Set Up Monthly Token Refresh (Cron)

Long-lived tokens expire after 60 days. Add a monthly cron job to refresh automatically:

```bash
crontab -e
```

Add the following line (adjust the path):

```cron
0 9 1 * * /Users/<your-username>/horizn/scripts/refresh_token.sh >> /tmp/horizn_token_refresh.log 2>&1
```

This runs `refresh_token.sh` at 09:00 on the 1st of every month. The script calls the Meta API to extend the token and updates `.env` automatically.

---

## Troubleshooting

| Error | Likely cause |
|---|---|
| `OAuthException (code 190)` | Token expired — run `./scripts/refresh_token.sh` manually |
| `OAuthException (code 10)` | Missing permission — re-run the OAuth flow |
| `400 Invalid parameter` | IG account not linked to a Facebook Page (step 2) |
