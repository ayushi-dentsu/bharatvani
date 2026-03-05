# Nova 2 Sonic Health Intake Agent — Local Setup Guide

## Prerequisites

- Python 3.12+ (the `aws-sdk-bedrock-runtime` package requires ≥3.12)
- AWS credentials with access to:
  - `bedrock:InvokeModelWithBidirectionalStream` for `amazon.nova-2-sonic-v1:0`
  - `s3:PutObject` on the target bucket
- A working microphone and speaker/headphones

---

## macOS Setup

### 1. Install Python 3.12

```bash
brew install python@3.12
```

### 2. Install PortAudio (required for PyAudio)

```bash
brew install portaudio
```

### 3. Create virtual environment

```bash
python3.12 -m venv venv
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install pyaudio boto3 aws-sdk-bedrock-runtime smithy-aws-core
```

### 5. Set AWS credentials

The script uses environment variables (not `~/.aws/credentials`):

```bash
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id)
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key)
export AWS_DEFAULT_REGION=us-east-1
```

If using a named profile:

```bash
eval $(aws configure export-credentials --profile your-profile --format env)
```

### 6. Find your audio devices

```bash
python nova_sonic_health_intake_agent.py --list-audio-devices --s3-bucket ivr-call-recordings-797882812707-us-east-1
```

Look for your mic (`[IN]`) and speaker (`[OUT]`) indices.

### 7. Run

```bash
python nova_sonic_health_intake_agent.py \
  --s3-bucket ivr-call-recordings-797882812707-us-east-1 \
  --input-device-index <MIC_INDEX> \
  --output-device-index <SPEAKER_INDEX>
```

---

## Windows Setup

### 1. Install Python 3.12

Download from https://www.python.org/downloads/ — check "Add to PATH" during install.

### 2. Create virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install pyaudio boto3 aws-sdk-bedrock-runtime smithy-aws-core
```

If `pyaudio` fails, install the prebuilt wheel:

```powershell
pip install pipwin
pipwin install pyaudio
```

### 4. Set AWS credentials

```powershell
$env:AWS_ACCESS_KEY_ID = "your-access-key"
$env:AWS_SECRET_ACCESS_KEY = "your-secret-key"
$env:AWS_DEFAULT_REGION = "us-east-1"
```

### 5. Find audio devices and run

```powershell
python nova_sonic_health_intake_agent.py --list-audio-devices --s3-bucket ivr-call-recordings-797882812707-us-east-1

python nova_sonic_health_intake_agent.py `
  --s3-bucket ivr-call-recordings-797882812707-us-east-1 `
  --input-device-index <MIC_INDEX> `
  --output-device-index <SPEAKER_INDEX>
```

---

## CLI Reference

| Argument | Default | Description |
|---|---|---|
| `--s3-bucket` | (required) | S3 bucket for uploads |
| `--model-id` | `amazon.nova-2-sonic-v1:0` | Bedrock model ID |
| `--region` | `us-east-1` | AWS region |
| `--voice-id` | `arjun` | Nova Sonic voice |
| `--input-device-index` | system default | PyAudio mic index |
| `--output-device-index` | system default | PyAudio speaker index |
| `--cough-seconds` | `8` | Cough recording duration |
| `--debug-events` | off | Log all streaming events |
| `--debug-audio` | off | Log audio chunk details |
| `--list-audio-devices` | — | List devices and exit |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: aws-sdk-bedrock-runtime` | You need Python ≥3.12. Check with `python --version`. |
| `SmithyIdentityError: AWS_ACCESS_KEY_ID required` | Export credentials as env vars (see step 5). The SDK doesn't read `~/.aws/credentials`. |
| No audio output | Run `--list-audio-devices`, verify your speaker index. Try without `--output-device-index` to use system default. |
| No mic input / timeouts | Check mic index. On macOS, grant terminal mic permission in System Settings → Privacy → Microphone. |
| `SigV4AuthScheme` errors | Update packages: `pip install --upgrade aws-sdk-bedrock-runtime smithy-aws-core` |
| Agent repeats questions (audio) | This is a known Nova Sonic behavior — duplicate audio is suppressed in code. If persistent, try `--debug-events` to diagnose. |
| No beep before cough | Verify `--output-device-index` points to your speaker. |
| `InvalidStateError: CANCELLED` on exit | Harmless CRT teardown noise, can be ignored. |
