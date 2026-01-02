# AI Agent for Doctor Appointment Booking & Front Desk

An intelligent agent that can:
1. **Make outbound calls** to doctor's offices to schedule appointments on your behalf
2. **Handle inbound calls** as a doctor office front desk, answering calls and scheduling appointments

Supports ultra-low latency real-time voice calls using OpenAI GPT-4o Realtime API or Azure Voice Live API.

## Features

### Outbound Calling (Appointment Booking)
- **OpenAI Mode**: Ultra-low latency (200-300ms) real phone calls using OpenAI GPT-4o Realtime API
- **Azure Mode**: Ultra-low latency real phone calls using Azure Voice Live API with advanced audio processing

### Inbound Calling (Doctor Office Front Desk)
- **OpenAI Inbound Mode**: Answers incoming calls as a doctor office front desk receptionist
- **Azure Inbound Mode**: Answers incoming calls using Azure's voice technology
- **Appointment Scheduling**: Schedules appointments with doctors based on availability
- **Professional Greeting**: Greets callers professionally as the front desk and handles calls

### General Features
- **Configurable Info**: Store patient/assistant details in JSON config files
- **Conversation Logging**: Saves call transcripts for review

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Information

#### For Outbound Calls (Appointment Booking)

Edit [patient_info.json](patient_info.json) with your details:

```json
{
  "name": "Your Name",
  "date_of_birth": "January 1, 1990",
  "phone": "(555) 123-4567",
  "reason_for_visit": "Your reason for the appointment",
  "preferred_time": "Your preferred time",
  "insurance": "Your insurance provider",
  "additional_notes": "Any special instructions for the agent"
}
```

#### For Inbound Calls (Doctor Office Front Desk)

Edit [assistant_info.json](assistant_info.json) with your clinic details:

```json
{
  "clinic_name": "Your Clinic Name",
  "role": "front_desk",
  "greeting_message": "Thank you for calling [Clinic Name]. This is the front desk. How can I help you today?",
  "doctors": {
    "doctor1": {
      "name": "Dr. Name",
      "availability": {
        "next_week": {
          "monday": "available",
          "tuesday": "available"
        },
        "current_week": "fully_booked"
      }
    }
  },
  "special_instructions": "You are the front desk receptionist. Help callers schedule appointments. Collect patient name, reason for visit, and preferred appointment time."
}
```

**Note:** The `greeting_message` is what the AI will say immediately when someone calls. The AI will speak this greeting using its natural voice (not Twilio TTS), so it sounds more human and conversational.

### 3. Set Up API Keys

Configure your credentials in the `.env` file:

```bash
# Twilio (required for all phone modes)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890

# OpenAI (for openai mode)
OPENAI_API_KEY=sk-proj-your_actual_api_key_here

# Azure (for azure mode)
AZURE_VOICELIVE_API_KEY=your_azure_api_key_here
AZURE_VOICELIVE_ENDPOINT=https://your-endpoint.azure.com
```

Make sure to use SJ-55 VPN

**Note:** The `.env` file is already created for you. Just edit it with your credentials. It's automatically ignored by git to keep your credentials secure.

### 4. Set up ngrok

Set up a public webhook URL using [ngrok](https://ngrok.com/):

```bash
# Install ngrok
brew install ngrok  # macOS
# or download from https://ngrok.com/download

# Start ngrok tunnel
ngrok http 5001
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.dev`) for use with the `--webhook` parameter.

## Usage

### Outbound Calls (Making Appointment Calls)

#### OpenAI Mode (OpenAI GPT-4o) - Recommended

Make ultra-low latency real phone calls using OpenAI's GPT-4o Realtime API:

```bash
python3 agent.py --mode openai \
  --phone +1234567890 \
  --webhook https://your-ngrok-url.ngrok-free.dev
```

**Parameters:**
- `--phone`: Doctor's office phone number in E.164 format (e.g., +1234567890)
- `--webhook`: Your public webhook URL (use ngrok for local testing)
- `--port`: Server port (default: 5001)

**Features:**
- Ultra-low latency (200-300ms)
- Natural conversation with interruption handling
- Real-time bidirectional audio streaming
- Excellent audio quality

#### Azure Mode

Make ultra-low latency real phone calls using Azure Voice Live API:

```bash
python3 agent.py --mode azure \
  --phone +1234567890 \
  --webhook https://your-ngrok-url.ngrok-free.dev
```

**Features:**
- Ultra-low latency similar to OpenAI Realtime
- Advanced audio processing (echo cancellation, noise suppression)
- Azure's enterprise-grade infrastructure
- Customizable voice selection

### Inbound Calls (Doctor Office Front Desk)

#### OpenAI Inbound Mode (OpenAI GPT-4o) - Recommended

Answer incoming calls as a doctor office front desk receptionist:

```bash
python3 agent.py --mode openai-inbound \
  --webhook https://your-ngrok-url.ngrok-free.dev
```

**Setup:**
1. Start the agent with the command above
2. **The Twilio webhook will be automatically updated!** 🎉
   - No need to manually configure Twilio Console anymore
   - The agent will automatically update your phone number's webhook to the new ngrok URL
   - This happens every time you restart the server with a new ngrok URL
3. Now when someone calls your Twilio number, the AI front desk will answer!

**Manual Configuration (if auto-update fails):**
If the automatic update doesn't work, you can manually configure in Twilio Console:
   - Go to Twilio Console → Phone Numbers
   - Select your phone number
   - Under "Voice & Fax", set:
     - **A CALL COMES IN**: Webhook
     - **URL**: `https://your-ngrok-url.ngrok-free.dev/incoming-call`
     - **HTTP**: POST

**What it does:**
- Greets callers professionally as the front desk
- Helps schedule appointments with available doctors
- Checks doctor availability based on the configuration
- Collects patient information (name, reason for visit, preferred time)
- Handles calls naturally with ultra-low latency

#### Azure Inbound Mode

Answer incoming calls using Azure Voice Live API:

```bash
python3 agent.py --mode azure-inbound \
  --webhook https://your-ngrok-url.ngrok-free.dev
```

Same setup as OpenAI Inbound, but using Azure's voice technology.

### Important Notes:
- Keep the terminal running - it acts as the webhook server
- The ngrok URL must be running and accessible
- For outbound calls: Twilio initiates the call
- For inbound calls: Twilio forwards incoming calls to your webhook
- Call logs and transcripts are saved in the `call_logs/` directory

## Custom Patient Configuration

Use a different config file:

```bash
python agent.py --config my_custom_config.json
```

## Examples

### Example 1: Making an Outbound Appointment Call (OpenAI Mode)

```bash
# Terminal 1: Start ngrok
ngrok http 5001

# Terminal 2: Make the call with OpenAI
python3 agent.py --mode openai \
  --phone +15551234567 \
  --webhook https://abc123.ngrok-free.dev
```

### Example 2: Making an Outbound Call with Azure

```bash
# Terminal 1: Start ngrok
ngrok http 5001

# Terminal 2: Make the call with Azure
python3 agent.py --mode azure \
  --phone +15551234567 \
  --webhook https://abc123.ngrok-free.dev
```

### Example 3: Running as Doctor Office Front Desk (Inbound Calls)

```bash
# Terminal 1: Start ngrok
ngrok http 5001

# Terminal 2: Start the front desk
python3 agent.py --mode openai-inbound \
  --webhook https://abc123.ngrok-free.dev

# Terminal 3: Configure Twilio
# Go to Twilio Console and set your phone number's webhook to:
# https://abc123.ngrok-free.dev/incoming-call

# Now call your Twilio number and the AI front desk will answer!
```

### Example 4: Doctor Office Front Desk with Azure

```bash
# Terminal 1: Start ngrok
ngrok http 5001

# Terminal 2: Start the assistant with Azure
python3 agent.py --mode azure-inbound \
  --webhook https://abc123.ngrok-free.dev
```

## Architecture

- [agent.py](agent.py): Main application with four modes:
  - `openai`: Outbound calls with OpenAI
  - `azure`: Outbound calls with Azure
  - `openai-inbound`: Inbound calls with OpenAI
  - `azure-inbound`: Inbound calls with Azure
- [patient_info.json](patient_info.json): Patient configuration for outbound appointment calls
- [assistant_info.json](assistant_info.json): Front desk configuration for inbound doctor office calls
- [openai_voice_service.py](openai_voice_service.py): OpenAI Realtime API integration
- [azure_voice_service.py](azure_voice_service.py): Azure Voice Live API integration

## Troubleshooting

### OpenAI API Key Issues

Make sure your OpenAI API key is set in `.env`:
```bash
OPENAI_API_KEY=sk-proj-your_actual_key_here
```

### Azure API Issues

Make sure your Azure credentials are set in `.env`:
```bash
AZURE_VOICELIVE_API_KEY=your_azure_api_key_here
AZURE_VOICELIVE_ENDPOINT=https://your-endpoint.azure.com
```

### Twilio Webhook Issues

- Ensure ngrok is running: `ngrok http 5001`
- Use the HTTPS URL from ngrok, not HTTP
- Check that your Twilio credentials are set correctly
- Verify the phone number format is E.164 (e.g., +1234567890)

### Call Logs

All phone conversations are saved in the `call_logs/` directory as JSON files with the Call SID as the filename.

## Cost Considerations

### OpenAI Mode
- **Input audio**: $0.06 per minute
- **Output audio**: $0.24 per minute
- **OpenAI Total**: ~$0.30 per minute
- **Plus Twilio**: ~$0.013/minute (US)
- **Total estimated cost**: ~$0.31-0.32 per minute
- **Best for**: Ultra-low latency, excellent user experience, natural conversation

### Azure Mode
- **Pricing**: Varies by Azure Voice Live pricing tier
- **Plus Twilio**: ~$0.013/minute (US)
- **Best for**: Enterprise deployments, advanced audio processing, customizable voices

See [Twilio Pricing](https://www.twilio.com/voice/pricing) and [OpenAI Pricing](https://openai.com/api/pricing/) for details.

## Security & Privacy

- Never commit your `patient_info.json` with real data to version control
- Keep Twilio credentials in environment variables, not in code
- Call logs may contain sensitive information - handle appropriately
- Consider HIPAA compliance if handling real medical information

## Future Enhancements

- [ ] Support for multiple languages
- [ ] Integration with calendar systems
- [ ] Confirmation emails/SMS after booking
- [ ] Support for rescheduling and cancellation
- [ ] More sophisticated natural language understanding
- [ ] Integration with EHR systems
