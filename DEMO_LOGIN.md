# Local evaluation login

This build includes a local evaluation login for controlled testing. It is not intended as a production identity provider.

Initial accounts (all initial passwords are `admin`):

| Username | Profile | Access |
|---|---|---|
| `admin` | Platform Administrator | Full administration and project access |
| `project_manager` | Project Manager | Project management without platform administration |
| `researcher` | Researcher | Create and edit research records |
| `reviewer` | Quality Reviewer | Read-only project access and review-oriented profile |
| `viewer` | Read-only Viewer | Read-only access |

Administrators can open **Administration → Local users & profiles**, select a profile, and use **Copy selected profile** to create a new username with the same rights. The copied account initially uses password `admin`.

The local store hashes passwords using PBKDF2-HMAC-SHA256 with a unique random salt, uses constant-time verification, and temporarily locks an account after repeated failures. The deliberately weak shared evaluation password must not be used for production deployments; configure OAuth/OIDC or SAML and disable local demo users for production.
