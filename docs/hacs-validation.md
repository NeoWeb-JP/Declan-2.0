# HACS validation for the proprietary custom repository

Declan remains proprietary/all rights reserved under the owner's 17 November
2026 decision. The root [LICENSE](../LICENSE) is a proprietary notice, not an
open-source licence.

The `HACS (proprietary custom repository)` CI job runs on every pull request to
main, every push to main and manual dispatch. All applicable checks are blocking
except `license`, which is explicitly excluded. Description, topics, integration
manifest, HACS manifest, issues and branding checks remain enabled. The job uses
a commit-pinned official HACS action, read-only repository access and no PR
comments. The upstream action's container image is maintained by HACS.

The repository description identifies Declan as proprietary; its topics describe
Home Assistant, custom integrations and voice assistants. The integration's
existing local brand icon satisfies the branding requirement.

The workflow is suitable for this custom repository. It is not a claim of HACS
default-catalog eligibility: catalog review does not accept ignored checks, and
the upstream licence validator rejects GitHub's `NOASSERTION` classification for
the proprietary notice. Do not change the licence to make that check pass.

Required merge-check enforcement is a separate GitHub branch-protection setting.
Use the exact check name above when requiring it for `main`; the workflow has no
path filters so unrelated pull requests still report a result.

References: [HACS validation documentation](https://contributors.home-assistant.io/marketplace/reference/validation/)
and [upstream licence validator](https://github.com/hacs/integration/blob/8a543828351b963438a1613a6f06332138e4f4d6/custom_components/hacs/validate/license.py).
