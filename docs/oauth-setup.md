# Enable OAuth sign-in

The service already implements OAuth. These steps connect it to your provider. Keep client secrets in `.env`; do not send them in chat or commit them.

## First administrator

Open http://localhost:8000 and create your administrator with your chosen credentials and `MOSS_SETUP_TOKEN` from `.env`. Then connect OAuth in Settings. New team members can use a matching email invitation to sign in with a provider.

## GitHub

Follow [GitHub's OAuth app registration guide](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app). For the current local service, register:

| Setting | Value |
| --- | --- |
| Application name | MossCMS |
| Homepage URL | `http://localhost:8000` |
| Authorization callback URL | `http://localhost:8000/auth/oauth/github/callback` |

Add your registered application's values to `.env`:

```dotenv
MOSS_GITHUB_CLIENT_ID=your_client_id
MOSS_GITHUB_CLIENT_SECRET=your_client_secret
```

## Google

Follow [Google's OpenID Connect setup instructions](https://developers.google.com/identity/openid-connect/openid-connect) to create OAuth credentials and configure the consent screen. Use a web application client with the redirect URI `http://localhost:8000/auth/oauth/oidc/callback`.

Add:

```dotenv
MOSS_OIDC_NAME=Google
MOSS_OIDC_DISCOVERY_URL=https://accounts.google.com/.well-known/openid-configuration
MOSS_OIDC_CLIENT_ID=your_client_id
MOSS_OIDC_CLIENT_SECRET=your_client_secret
```

## Another OpenID Connect provider

Create a confidential web application client using the provider's discovery document and the redirect URI `http://localhost:8000/auth/oauth/oidc/callback`. Enable `openid email profile`, and ensure the provider returns `email_verified: true` for verified accounts. Set `MOSS_OIDC_NAME`, `MOSS_OIDC_DISCOVERY_URL`, `MOSS_OIDC_CLIENT_ID`, and `MOSS_OIDC_CLIENT_SECRET` in `.env`.

## Apply configuration

```sh
docker compose up -d app
```

Refresh the admin page. Existing users sign in locally and choose **Settings → Connect provider**. Then sign out and use **Continue with provider**. An existing account must be explicitly linked first; an email match does not link it automatically.

For a hosted instance, replace localhost with `MOSS_PUBLIC_URL` in both the registered homepage and callback. Provider registration and MossCMS must use exactly the same callback URL. Preserve `/auth/oauth/github/callback` or `/auth/oauth/oidc/callback`. Set the public URL and trusted origins to HTTPS when using production mode.
