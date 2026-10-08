# calendar-goog-link

## Project Overview
This project is a static HTML/CSS/JavaScript website designed for GitHub Pages that integrates directly with Google Calendar using the Google Calendar API. Sign-in uses **Google Identity Services (GIS)** — the current, supported OAuth library. (An earlier version of this project used `gapi.auth2`, which Google has deprecated; that's why sign-in never actually worked before.)

## File Structure
```
calendar-goog-link
├── index.html
├── style.css
├── script.js
└── README.md
```

## Setup Instructions

### Enabling Google Calendar API
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing project.
3. Navigate to the "APIs & Services" > "Library" section.
4. Search for "Google Calendar API" and enable it for your project.
5. Go to "APIs & Services" > "Credentials".
6. Click "Create Credentials" and select "OAuth client ID".
7. Configure the OAuth consent screen if prompted (External is fine for personal use; add your own Google account as a test user if the app stays in "Testing" mode).
8. Set the application type to "Web application".
9. Add the following Authorized JavaScript origins:
   - `https://yagiht.github.io`
   - `http://localhost:PORT` (optional, for local testing — pick any port you serve the site on)
10. You do **not** need to set an Authorized redirect URI — Google Identity Services' token flow used here doesn't redirect.
11. After creating the credentials, copy the `Client ID` (looks like `xxxxx.apps.googleusercontent.com`).

### Adding CLIENT_ID in script.js
Open `script.js` and set the `CLIENT_ID` constant near the top:
```javascript
const CLIENT_ID = 'YOUR_CLIENT_ID_HERE.apps.googleusercontent.com';
```

### Deployment on GitHub Pages
1. Push your code to a GitHub repository named `calendar-goog-link`.
2. Go to the repository's Settings > Pages.
3. Select the branch to deploy (usually `main`).
4. Save. Your site will be published at `https://yagiht.github.io/calendar-goog-link/`.
5. Make sure that exact URL's origin (`https://yagiht.github.io`) is listed under Authorized JavaScript origins in step 9 above — a mismatch here is the most common reason sign-in fails.

### Testing locally
Because this uses OAuth, you can't just open `index.html` as a `file://` URL — serve it over http(s), e.g.:
```bash
python3 -m http.server 8000
```
then visit `http://localhost:8000`, having added that origin to the OAuth client as described above.

## Functionality
- Users click "Sign in with Google" to authorize the app for calendar access (via Google Identity Services).
- Once signed in, "Add To-Do to Calendar" opens a modal to enter a title, urgency, and date/time.
- Submitting the form creates an event in the user's primary Google Calendar.
- "Sign out" revokes the current session token.

## Troubleshooting
- **Nothing happens when clicking "Add To-Do to Calendar"**: that button is disabled until you're signed in.
- **Sign-in popup closes immediately / errors**: double-check the Authorized JavaScript origin exactly matches the page's origin (protocol + domain, no trailing path), and that the OAuth consent screen has your Google account added as a test user if it's still in "Testing" status.
- **Console shows a 403 from the Calendar API**: the Google Calendar API likely isn't enabled on the Cloud project tied to your Client ID.

## Acknowledgments
This project utilizes the Google Calendar API and the gapi JavaScript client library, together with Google Identity Services for authentication.
