# Oracle Deployment Scripts

These scripts target the existing Oracle VM with static IP `80.225.242.6`.

Oracle is the ICICI Breeze static-IP boundary. AWS calls Oracle; Oracle calls Breeze.

Dry run:

```bash
oracle/scripts/deploy_oracle_services.sh --dry-run
```

Real deploy requires:

```bash
export ORACLE_HOST=80.225.242.6
export ORACLE_USER=opc
export ORACLE_SSH_KEY=/path/to/oracle_private_key
export ORACLE_PROXY_SHARED_SECRET=change-me
oracle/scripts/deploy_oracle_services.sh
```

The script copies `oracle/` to the VM, writes a remote `.env`, runs Docker Compose, and checks:

- execution proxy: `http://127.0.0.1:8080/health`
- market collector: `http://127.0.0.1:8090/health`

`deploy_execution_proxy.sh` remains as a compatibility wrapper around the unified script.
