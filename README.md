# Sovereign Dynamic Family Cloud

**A source-available initiative to build a modular, expandable, and sovereign family cloud across Europe.**

## About the Project

Dynamic Family Cloud explores how families can build and operate their own distributed cloud infrastructure while maintaining control over their data, security, and digital services.

The initial architecture connects sites in Belgium 🇧🇪 and Spain 🇪🇸, with the possibility of extending the infrastructure to additional locations.

The project focuses on:

- **Digital sovereignty:** Favoring European infrastructure and services while reducing unnecessary external dependencies.
- **Modular architecture:** Allowing networking, storage, and computing capabilities to evolve independently.
- **Secure connectivity:** Establishing encrypted communications between geographically distributed sites.
- **Zero-Touch Provisioning:** Simplifying device deployment through cryptographic identity and automated network enrollment after initial preparation.
- **Open-source technologies:** Building a transparent, reproducible infrastructure.

## Repository Purpose

This public repository provides the technical documentation, configuration examples, and selected test scripts accompanying the Dynamic Family Cloud project.

The development environment is maintained separately. Only reviewed, publication-ready materials are included here.

Articles explaining the project's architecture, design decisions, and development journey are published separately on Medium.

## Documentation

### Part 2 — European Control Plane

The second phase establishes the network coordination and device admission infrastructure.

It uses OVHcloud, Traefik, Actalis, Headscale, Tailscale, and a custom Ed25519-based Admission service.

The following technical guides are available:

| Guide | Description |
|---|---|
| [01 — Creating an OVHcloud VPS](docs/part-2-control-plane/01_Guide_creation_VPS_OVH.md) | VPS provisioning, Debian installation, SSH access, and network security. |
| [02 — VPS Configuration](docs/part-2-control-plane/02_Guide_configuration_VPS_GitHub.md) | Deployment of Traefik, Headscale, Actalis TLS, and the Admission service. |
| [03 — Testing and Validation](docs/part-2-control-plane/03_Guide_tests_validation.md) | Connectivity checks, cryptographic authentication, replay protection, enrollment, and revocation. |

Companion test scripts are located in `docs/part-2-control-plane/tests/`.

## Project Status

The European control-plane prototype has been implemented and tested using a simulated device running a real Tailscale client.

Physical device provisioning, cross-site networking, failover, disaster recovery, and some security-hardening procedures remain under development or validation.

This project is experimental and does not claim formal security or regulatory certification.

## Development and Publication

The project uses separate environments:

- **Development repository:** implementation, experimentation, and internal validation.
- **Public repository:** reviewed documentation, safe configuration examples, and reproducible test materials.

Secrets, private keys, deployment credentials, and operational databases are never intentionally included in the public repository.

## License

License information will be added once the project's public licensing terms have been selected.
