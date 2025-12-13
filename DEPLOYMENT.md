# Deployment Guide

This guide covers deploying the SMS Survey Engine to Fly.io with PostgreSQL and Twilio integration.

## Prerequisites

1. **Fly.io Account**: Sign up at https://fly.io/app/sign-up
2. **Fly.io CLI**: Install following instructions at https://fly.io/docs/hands-on/install-flyctl/
3. **Twilio Account**: Sign up at https://www.twilio.com/try-twilio
4. **Docker** (optional): For local testing of the container

### Verify Fly.io CLI Installation

```bash
flyctl version
# Should show version 0.0.200 or higher (required for features like auto_stop_machines and min_machines_running)

flyctl auth login
# Opens browser for authentication
```

## Initial Deployment

### 1. Launch the Application

From the project root directory:

```bash
# Launch the app (uses fly.toml configuration)
flyctl launch --no-deploy

# This creates the app on Fly.io but doesn't deploy yet
# It will read from fly.toml for configuration
```

If `fly.toml` doesn't exist or you want to customize:

```bash
flyctl launch --no-deploy
# Follow prompts:
# - App name: sms-survey-engine (or your choice)
# - Region: sjc (San Jose, California)
# - PostgreSQL: Yes (when prompted)
# - Redis: No
```

### 2. Create PostgreSQL Database

If you didn't create it during launch:

```bash
# Create a Postgres cluster
flyctl postgres create --name sms-survey-db --region sjc

# Attach it to your app (creates DATABASE_URL secret)
flyctl postgres attach sms-survey-db --app sms-survey-engine
```

This automatically sets the `DATABASE_URL` secret for your application.

### 3. Configure Secrets

The application requires 7 secrets total, but only 6 need to be manually set (`DATABASE_URL` is auto-configured). Set them using `flyctl secrets set`:

| Secret | Description | How to Generate |
|--------|-------------|-----------------|
| `DATABASE_URL` | PostgreSQL connection string | Auto-set by `postgres attach` |
| `TWILIO_ACCOUNT_SID` | Twilio account identifier | Get from https://console.twilio.com |
| `TWILIO_AUTH_TOKEN` | Twilio authentication token | Get from https://console.twilio.com |
| `TWILIO_PHONE_NUMBER` | Your Twilio phone number (E.164 format) | Get from Twilio console (e.g., +15551234567) |
| `SECRET_KEY` | Flask/FastAPI secret for sessions | `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` |
| `PHONE_HASH_SALT` | Salt for phone number hashing | `openssl rand -hex 64` |
| `DEFAULT_SURVEY_ID` | ID of default survey to use | `health_screening` (or your survey ID) |

#### Set All Secrets at Once

```bash
flyctl secrets set \
  TWILIO_ACCOUNT_SID="AC..." \
  TWILIO_AUTH_TOKEN="your_auth_token" \
  TWILIO_PHONE_NUMBER="+15551234567" \
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  PHONE_HASH_SALT="$(openssl rand -hex 64)" \
  DEFAULT_SURVEY_ID="health_screening" \
  --app sms-survey-engine
```

**CRITICAL:** Store your `PHONE_HASH_SALT` in a secure password manager. Changing it will orphan all existing survey sessions.

### 4. Deploy the Application

```bash
flyctl deploy --app sms-survey-engine
```

This will:
1. Build the Docker image
2. Push it to Fly.io registry
3. Run database migrations (`alembic upgrade head`)
4. Start the application
5. Run health checks

### 5. Verify Deployment

```bash
# Check app status
flyctl status --app sms-survey-engine

# View recent logs
flyctl logs --app sms-survey-engine

# Test health endpoint
curl https://sms-survey-engine.fly.dev/health
# Should return: {"status": "healthy"}
```

## Configure Twilio Webhook

Once deployed, configure Twilio to send incoming SMS to your application:

1. Go to https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
2. Click on your phone number
3. Scroll to "Messaging Configuration"
4. Set "A MESSAGE COMES IN" webhook:
   - **URL**: `https://sms-survey-engine.fly.dev/webhook/sms`
   - **HTTP Method**: POST
5. Click "Save"

### Test the Integration

Send a text message to your Twilio phone number. You should receive a consent prompt.

Check logs for webhook activity:

```bash
flyctl logs --app sms-survey-engine
```

## Database Setup

Database migrations run automatically during deployment via the `release_command` in `fly.toml`:

```toml
[deploy]
  release_command = 'alembic upgrade head'
```

### Manual Migration Commands

If needed, you can run migrations manually:

```bash
# SSH into the running app
flyctl ssh console --app sms-survey-engine

# Run migrations
alembic upgrade head

# Check current migration
alembic current

# Exit
exit
```

### Database Console Access

```bash
# Connect to Postgres cluster
flyctl postgres connect --app sms-survey-db

# Run SQL queries
SELECT * FROM alembic_version;
SELECT survey_id, COUNT(*) FROM survey_sessions GROUP BY survey_id;
```

## Monitoring and Logs

### View Logs

```bash
# Stream live logs
flyctl logs --app sms-survey-engine

# Filter by level
flyctl logs --app sms-survey-engine | grep ERROR

# View specific number of recent entries
flyctl logs --app sms-survey-engine -n 100
```

### Metrics and Dashboard

Visit your app dashboard: https://fly.io/apps/sms-survey-engine

Monitor:
- Request rate and latency
- Memory usage
- CPU usage
- Health check status
- Active machines

### Scaling

```bash
# Scale to 2 instances minimum
flyctl scale count 2 --app sms-survey-engine

# Scale to different VM size
flyctl scale vm shared-cpu-2x --app sms-survey-engine

# Scale memory
flyctl scale memory 512 --app sms-survey-engine
```

## Updates and Redeployment

### Deploy Code Changes

```bash
# After committing changes
git push

# Deploy to Fly.io
flyctl deploy --app sms-survey-engine
```

### Update Secrets

```bash
# Update a single secret
flyctl secrets set TWILIO_AUTH_TOKEN="new_token" --app sms-survey-engine

# View configured secrets (values are hidden)
flyctl secrets list --app sms-survey-engine

# Unset a secret
flyctl secrets unset SECRET_NAME --app sms-survey-engine
```

### Update Survey Definitions

Survey YAML files are bundled in the Docker image. To update surveys:

1. Edit survey files in `surveys/` directory
2. Commit changes
3. Redeploy: `flyctl deploy --app sms-survey-engine`

## Rollback Procedures

### Rollback to Previous Release

```bash
# List recent releases
flyctl releases --app sms-survey-engine

# Rollback to previous version
flyctl releases rollback --app sms-survey-engine

# Rollback to specific version
flyctl releases rollback v5 --app sms-survey-engine
```

### Database Migration Rollback

```bash
# SSH into app
flyctl ssh console --app sms-survey-engine

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>

exit
```

**WARNING:** Database rollbacks can cause data loss. Always backup first:

```bash
flyctl postgres db dump --app sms-survey-db > backup_$(date +%Y%m%d_%H%M%S).sql
```

## Troubleshooting

### App Won't Start

**Symptoms:** Health checks failing, app crashes immediately

**Diagnosis:**

```bash
flyctl logs --app sms-survey-engine
```

**Common causes:**

1. **Missing secrets**: Check all required secrets are set (6 manual + 1 auto-configured)
   ```bash
   flyctl secrets list --app sms-survey-engine
   ```

2. **Database connection failed**: Verify DATABASE_URL
   ```bash
   flyctl ssh console --app sms-survey-engine
   echo $DATABASE_URL
   ```

3. **Migration failure**: Check release command logs
   ```bash
   flyctl logs --app sms-survey-engine | grep "release_command"
   ```

### Health Checks Failing

**Symptoms:** `/health` endpoint returns 5xx or times out

**Diagnosis:**

```bash
# Check if app is listening on port 8000
flyctl ssh console --app sms-survey-engine
netstat -tlnp | grep 8000
```

**Solutions:**

1. Verify `EXPOSE 8000` in Dockerfile matches `internal_port` in fly.toml
2. Check if uvicorn is running: `ps aux | grep uvicorn`
3. Test health endpoint locally inside container:
   ```bash
   curl http://localhost:8000/health
   ```

### Webhooks Not Working

**Symptoms:** Twilio returns errors, no logs when texting

**Diagnosis:**

1. Check Twilio webhook configuration points to correct URL
2. Verify webhook signature validation:
   ```bash
   flyctl logs --app sms-survey-engine | grep "webhook"
   ```

**Common issues:**

1. **Incorrect webhook URL**: Must be `https://your-app.fly.dev/webhook/sms`
2. **Signature validation failing**: Verify `TWILIO_AUTH_TOKEN` is correct
3. **Phone number format**: Twilio sends E.164 format (e.g., +15551234567)

**Test webhook manually:**

```bash
curl -X POST https://sms-survey-engine.fly.dev/webhook/sms \
  -d "From=+15551234567" \
  -d "Body=test"
```

### High Memory Usage

**Symptoms:** App crashes with OOM (out of memory) errors

**Diagnosis:**

```bash
flyctl metrics --app sms-survey-engine
```

**Solutions:**

1. Scale memory: `flyctl scale memory 512 --app sms-survey-engine`
2. Check for memory leaks in logs
3. Review SQLAlchemy session management (ensure sessions are closed)

### Migration Failures

**Symptoms:** Deployment fails during `release_command`

**Diagnosis:**

```bash
flyctl logs --app sms-survey-engine | grep alembic
```

**Common causes:**

1. **Syntax error in migration**: Fix migration file and redeploy
2. **Schema conflict**: Database already has conflicting tables
3. **Connection timeout**: Database unreachable

**Manual fix:**

```bash
# SSH into app
flyctl ssh console --app sms-survey-engine

# Check migration status
alembic current

# Force set version (if migration ran but failed to record)
alembic stamp head

exit
```

## Production Checklist

Before going live with real users:

- [ ] All secrets configured correctly (6 manual + DATABASE_URL auto-configured)
- [ ] DATABASE_URL points to production Postgres cluster
- [ ] PHONE_HASH_SALT is backed up securely (cannot recover if lost)
- [ ] Twilio webhook URL configured and tested
- [ ] Health endpoint returns 200 OK
- [ ] Send test SMS and receive consent prompt
- [ ] Complete a full survey flow end-to-end
- [ ] Monitor logs for errors during test
- [ ] Review survey YAML files for typos
- [ ] Set up monitoring/alerting (Fly.io dashboard or external)
- [ ] Document emergency contacts (Twilio, Fly.io support)
- [ ] Test opt-out flow (send STOP keyword)
- [ ] Scale to minimum 1 machine: `flyctl scale count 1`

## Security Best Practices

1. **Secrets Management**:
   - Never commit secrets to git
   - Store PHONE_HASH_SALT in password manager
   - Rotate TWILIO_AUTH_TOKEN periodically

2. **HTTPS Only**:
   - `force_https = true` in fly.toml ensures all traffic is encrypted
   - Twilio webhooks must use HTTPS

3. **Database Security**:
   - Use Fly.io private network for database connections
   - Regular backups: `flyctl postgres db dump`

4. **Monitoring**:
   - Set up log aggregation for security events
   - Monitor for unusual patterns (rapid SMS from single hash)
   - Alert on health check failures

5. **Rate Limiting**:
   - Implement in Phase 9 (not yet deployed)
   - Use Twilio's built-in rate limits as first line of defense

6. **Data Privacy**:
   - Phone numbers are hashed, never stored plaintext
   - Logs truncate hashes to 12 characters
   - Implement data deletion process for GDPR/CCPA compliance

## Additional Resources

- Fly.io Documentation: https://fly.io/docs/
- Twilio SMS Documentation: https://www.twilio.com/docs/sms
- FastAPI Deployment: https://fastapi.tiangolo.com/deployment/
- Alembic Migrations: https://alembic.sqlalchemy.org/
- Project Implementation Plan: `plans/implementation-plan.md`
- Survey Format Guide: `surveys/README.md`
