# Deployment (AWS EC2)

One EC2 instance (`i-09443d171c373c90b`, ap-south-1, Amazon Linux 2023, t3.small) runs the API container
`0008a/adaptivephish:<short-sha>` from Docker Hub. Deploys come only from the `Deploy to EC2` workflow.

## Security model

- **No SSH, no key pair, no inbound port 22.** Commands reach the instance through AWS Systems Manager Run Command
  (instance role `adaptivephish-ec2-role` with `AmazonSSMManagedInstanceCore` only).
- **GitHub to AWS uses OIDC**, no stored AWS keys. Role `adaptivephish-gha-deploy` can only call `ssm:SendCommand`
  on `AWS-RunShellScript` and this one instance, plus read command results.
- **Approval gate.** The job runs in the GitHub environment `production` with a required reviewer; the role's trust
  policy only accepts tokens from that environment.
- **Pre-deploy checks.** The tag must match `^[0-9a-f]{7}$` (or `previous`), have a green `Build and push image`
  run, and exist on Docker Hub. The image is public, so the instance holds no registry credentials.
- **Config outside the image.** An optional `/opt/adaptivephish/api.env` is passed to the container with
  `--env-file`. Nothing secret is baked into the image.
- **Security group** `adaptivephish-api-sg`: one inbound rule, TCP 8000 from the operator's /32. IMDSv2 only.

### Limitation: plain HTTP

The API is served over plain HTTP on port 8000 with no TLS and no authentication. It is protected only by the
security-group IP restriction, which is why it must never be opened to 0.0.0.0/0. Submitted URLs and scores cross
the network unencrypted. A production setup would put an ALB or CloudFront with an ACM certificate in front, plus
authentication. If the operator's IP changes, update the security-group rule.

## Deploying

Actions, then `Deploy to EC2`, then Run workflow with `image_tag` set to a short SHA, then approve in the run.
The instance script (`scripts/deploy/remote_deploy.sh`) pulls the image, replaces the container
(`--restart unless-stopped`, json-file logs capped at 3 x 10 MB), waits up to 90 s for `/health`, smoke-tests
`/predict` and checks `adaptivephish_model_loaded 1`. The workflow is green only if SSM reports Success.
If the new version fails, the script restarts the previous one and still fails the run.

## Version tracking

On the instance, in `/opt/adaptivephish/`: `current_tag`, `previous_tag` and `deployments.log` (UTC timestamps:
deployed / FAILED / rolled back). `GET /health` reports `model_version` and `feature_version`. The image tag is the
git short SHA, which ties code, `dvc.lock` and `models/production.json` together.
Check from outside: `curl http://15.206.211.173:8000/health`.

## Rollback

- **Normal:** run `Deploy to EC2` with `image_tag` = `previous` (reads `previous_tag`), or with an older short SHA
  that still has a green build run. Same approval, same smoke test.
- **Automatic:** a failed deploy restarts the last good tag.
- **Manual fallback (SSM Session Manager or Run Command, not SSH):**
  `docker rm -f adaptivephish-api; docker run -d --name adaptivephish-api --restart unless-stopped -p 8000:8000 0008a/adaptivephish:$(cat /opt/adaptivephish/previous_tag)`
- Limit: only one previous version is remembered. Older ones can be re-pulled from Docker Hub by tag (tags are
  short SHAs and never `latest`).
- Status: rollback has not been exercised yet, because only one version has been deployed.

## Problems met during the first deployment (and fixes)

1. **OIDC "Not authorized to perform sts:AssumeRoleWithWebIdentity".** Two causes:
   - The `sub` claim in this repository's tokens used GitHub's **immutable-ID format**,
     `repo:ajitjain04@149153509/Mlops-@1435573643:environment:production`, not the classic
     `repo:ajitjain04/Mlops-:environment:production`. The trust policy's `sub` condition was changed to match the
     format actually issued. To see the real value, print the decoded `sub` claim (never the token) in a throwaway step.
   - The environment variable `AWS_DEPLOY_ROLE_ARN` held the **OIDC provider ARN** instead of the role ARN
     (`arn:aws:iam::728603839244:role/adaptivephish-gha-deploy`). Fixed by correcting the variable.

   The temporary debug step used to diagnose this has been removed.
2. **Docker missing on the instance.** The user-data script did not run, so Docker was never installed. It was
   installed once through SSM Run Command (`dnf install -y docker; systemctl enable --now docker`).
   Lesson: after launch, check `docker --version` through SSM before the first deploy.

## Cost control and cleanup

Approximate costs (ap-south-1, check current pricing): t3.small about 0.02 USD/hour while running; a 20 GiB gp3 volume
about 2 USD/month whether running or stopped; the public IPv4 address about 0.005 USD/hour. The public IP is
auto-assigned, so it **changes after a stop/start**; update URLs and the smoke-test target.

- **Pause (stop the instance):** EC2 console, Instance state, Stop. Compute billing stops, the volume is still
  billed, and the container restarts on start (Docker is enabled and the container uses `--restart unless-stopped`).
- **Remove everything (terminate), in this order:**
  1. Terminate instance `i-09443d171c373c90b`; confirm the root volume is gone.
  2. Delete security group `adaptivephish-api-sg` (only after the instance is gone).
  3. Delete role `adaptivephish-ec2-role` (and its instance profile).
  4. Delete role `adaptivephish-gha-deploy`, and the OIDC provider `token.actions.githubusercontent.com` if nothing
     else uses it.
  5. Delete the GitHub environment `production` and its two variables.
- **S3 bucket `adaptivephish-dvc-ajit-2026` (DVC remote) is separate** and holds the data and model artifacts. Keep it
  while the project must stay reproducible: deleting it makes `dvc pull`, and the image build in CI, fail. To remove
  it, empty it first (`aws s3 rm s3://adaptivephish-dvc-ajit-2026 --recursive --profile adaptivephish`; check for
  versioned objects), delete the bucket, then delete IAM users `adaptivephish-dvc` and `adaptivephish-ci` and their keys.
- Docker Hub: delete the repository `0008a/adaptivephish` if it is no longer needed.
- Set an AWS Budgets alert so forgotten resources get noticed.
