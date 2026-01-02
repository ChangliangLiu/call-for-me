import json
import argparse
import sys
import os
from twilio.rest import Client
from openai_voice_service import OpenAIVoiceService, OpenAICallServer
from azure_voice_service import AzureVoiceService, AzureCallServer

def update_twilio_webhook(webhook_url, twilio_phone_number=None):
    """Automatically update Twilio phone number webhook to the new URL"""
    try:
        # Get Twilio credentials from environment
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        twilio_number = twilio_phone_number or os.environ.get('TWILIO_PHONE_NUMBER')

        if not all([account_sid, auth_token, twilio_number]):
            print("⚠️  Warning: Could not auto-update Twilio webhook (missing credentials)")
            return False

        client = Client(account_sid, auth_token)

        # Find the phone number resource
        incoming_phone_numbers = client.incoming_phone_numbers.list(phone_number=twilio_number)

        if not incoming_phone_numbers:
            print(f"⚠️  Warning: Phone number {twilio_number} not found in your Twilio account")
            return False

        phone_number_sid = incoming_phone_numbers[0].sid

        # Update the webhook URL
        voice_url = f"{webhook_url}/incoming-call"
        client.incoming_phone_numbers(phone_number_sid).update(
            voice_url=voice_url,
            voice_method='POST'
        )

        print(f"✅ Successfully updated Twilio webhook for {twilio_number}")
        print(f"   Voice URL: {voice_url}")
        return True

    except Exception as e:
        print(f"⚠️  Warning: Failed to auto-update Twilio webhook: {e}")
        print(f"   Please manually set your Twilio webhook to: {webhook_url}/incoming-call")
        return False

def load_patient_info(config_file='patient_info.json'):
    """Load patient information from JSON config file"""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file '{config_file}' not found!")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in '{config_file}'!")
        sys.exit(1)

def create_system_prompt(patient_info):
    """Create the system prompt for the agent based on patient info"""
    return f"""You are a personal AI assistant to help your owner to do calling a doctor's office to schedule an appointment. Here is the information you need to provide during the call:

Your details:
- Name: {patient_info['name']}
- Date of Birth: {patient_info['date_of_birth']}
- Phone: {patient_info['phone']}
- Reason for visit: {patient_info['reason_for_visit']}
- Preferred appointment time: {patient_info['preferred_time']}
- Insurance: {patient_info['insurance']}

Additional instructions: {patient_info.get('additional_notes', 'Be polite and professional')}

Your goal is to successfully schedule an appointment for your owner. Be polite, provide necessary information when asked, and ask clarifying questions if needed. Respond naturally as a real patient would.

The conversation starts when the receptionist answers the phone. Wait for them to greet you, then introduce yourself and state your purpose."""

def openai_phone_mode(patient_info, doctor_phone_number, webhook_url, port=5001):
    """Make a real phone call using OpenAI GPT-4o Realtime API (ultra-low latency)"""
    print("\n" + "="*60)
    print("DOCTOR APPOINTMENT BOOKING - OPENAI VOICE CALL")
    print("="*60)
    print(f"\nCalling: {doctor_phone_number}")
    print(f"Webhook URL: {webhook_url}")
    print(f"Local Port: {port}")
    print(f"Mode: OpenAI GPT-4o Realtime API (200-300ms latency)")
    print("="*60 + "\n")

    system_prompt = create_system_prompt(patient_info)

    # Create system instructions for OpenAI
    system_instructions = f"""You are an AI assistant making a phone call to schedule a doctor appointment.

{system_prompt}

Important behavioral guidelines:
- Speak naturally and conversationally, as a real patient would
- Keep responses concise (1-3 sentences)
- Listen carefully to the receptionist and respond appropriately
- If asked for information, provide it clearly
- Be polite and professional at all times
- If you successfully book an appointment, confirm the date, time, and any instructions
- End the call politely once the appointment is scheduled or if you cannot proceed"""

    try:
        # Initialize OpenAI Voice Service
        service = OpenAIVoiceService()

        # Create and start the OpenAI server
        server = OpenAICallServer(system_instructions)

        print("Starting OpenAI voice server...")
        print("Make sure your webhook URL is publicly accessible (use ngrok if testing locally)")
        print(f"Server will run on port {port} (HTTP + WebSocket on same port)")
        print("\nServer will handle bidirectional audio streaming with OpenAI.\n")

        # Make the call
        call_sid = service.make_call(doctor_phone_number, webhook_url)

        if call_sid:
            print(f"The agent is now making the call...\n")
            print("Real-time audio streaming active. Press Ctrl+C to stop.\n")

            # Run the server (this blocks)
            server.run(host='0.0.0.0', port=port)
        else:
            print("Failed to initiate call. Please check your Twilio credentials.")

    except ValueError as e:
        print(f"Error: {e}")
        print("\nPlease ensure the following environment variables are set:")
        print("  TWILIO_ACCOUNT_SID")
        print("  TWILIO_AUTH_TOKEN")
        print("  TWILIO_PHONE_NUMBER")
        print("  OPENAI_API_KEY")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[Call server stopped]\n")

def azure_phone_mode(patient_info, doctor_phone_number, webhook_url, port=5001):
    """Make a real phone call using Azure Voice Live API (ultra-low latency with Azure voice)"""
    print("\n" + "="*60)
    print("DOCTOR APPOINTMENT BOOKING - AZURE VOICE LIVE CALL")
    print("="*60)
    print(f"\nCalling: {doctor_phone_number}")
    print(f"Webhook URL: {webhook_url}")
    print(f"Local Port: {port}")
    print(f"Mode: Azure Voice Live API (ultra-low latency)")
    print("="*60 + "\n")

    system_prompt = create_system_prompt(patient_info)

    # Create system instructions for Azure
    system_instructions = f"""You are an AI assistant making a phone call to schedule a doctor appointment.

{system_prompt}

Important behavioral guidelines:
- Speak naturally and conversationally, as a real patient would
- Keep responses concise (1-3 sentences)
- Listen carefully to the receptionist and respond appropriately
- If asked for information, provide it clearly
- Be polite and professional at all times
- If you successfully book an appointment, confirm the date, time, and any instructions
- End the call politely once the appointment is scheduled or if you cannot proceed"""

    try:
        # Initialize Azure Voice Service
        service = AzureVoiceService()

        # Create and start the azure server (voice and model config loaded from .env)
        server = AzureCallServer(system_instructions)

        print("Starting Azure voice server...")
        print("Make sure your webhook URL is publicly accessible (use ngrok if testing locally)")
        print(f"Server will run on port {port} (HTTP + WebSocket on same port)")
        print("\nServer will handle bidirectional audio streaming with Azure Voice Live API.\n")

        # Make the call
        call_sid = service.make_call(doctor_phone_number, webhook_url)

        if call_sid:
            print(f"The agent is now making the call...\n")
            print("Real-time audio streaming active. Press Ctrl+C to stop.\n")

            # Run the server (this blocks)
            server.run(host='0.0.0.0', port=port)
        else:
            print("Failed to initiate call. Please check your Twilio credentials.")

    except ValueError as e:
        print(f"Error: {e}")
        print("\nPlease ensure the following environment variables are set:")
        print("  TWILIO_ACCOUNT_SID")
        print("  TWILIO_AUTH_TOKEN")
        print("  TWILIO_PHONE_NUMBER")
        print("  AZURE_VOICELIVE_API_KEY")
        print("  AZURE_VOICELIVE_ENDPOINT")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[Call server stopped]\n")

def create_assistant_prompt(assistant_info):
    """Create the system prompt for the front desk based on assistant info"""
    clinic_name = assistant_info.get('clinic_name', 'Allegaro Pediatrics')
    
    # Build doctor availability information
    doctors_info = []
    if 'doctors' in assistant_info:
        for doctor_key, doctor_data in assistant_info['doctors'].items():
            doctor_name = doctor_data.get('name', doctor_key.title())
            availability = doctor_data.get('availability', {})
            next_week_avail = availability.get('next_week', {})
            available_days = [day.title() for day, status in next_week_avail.items() if status == 'available']
            if available_days:
                doctors_info.append(f"- {doctor_name}: Available on {', '.join(available_days)} next week")
    
    doctors_availability = '\n'.join(doctors_info) if doctors_info else "Please check availability with the front desk."
    
    return f"""You are the front desk receptionist for {clinic_name}. You answer phone calls and help patients schedule appointments.

Your responsibilities:
- Answer phone calls professionally and courteously
- Help patients schedule appointments with available doctors
- Provide information about doctor availability
- Collect necessary information: patient name, reason for visit, preferred appointment time
- Be professional, friendly, and helpful

Doctor Availability:
{doctors_availability}

Important guidelines:
- Always identify yourself as the front desk for {clinic_name} at the beginning of the call
- Ask for the caller's name and how you can help them
- When scheduling appointments, confirm the patient's name, reason for visit, preferred doctor, and preferred time
- If a requested time is not available, suggest alternative times
- Be conversational and natural
- Confirm appointment details before ending the call

Special notes: {assistant_info.get('special_instructions', 'Handle all calls professionally and help with appointment scheduling')}"""

def openai_inbound_mode(assistant_info, webhook_url, port=5001):
    """Handle inbound calls using OpenAI GPT-4o Realtime API (front desk mode)"""
    clinic_name = assistant_info.get('clinic_name', 'Allegaro Pediatrics')
    print("\n" + "="*60)
    print(f"{clinic_name.upper()} - FRONT DESK - INBOUND CALLS")
    print("="*60)
    print(f"Webhook URL: {webhook_url}")
    print(f"Local Port: {port}")
    print(f"Mode: OpenAI GPT-4o Realtime API (200-300ms latency)")
    print("="*60 + "\n")

    system_prompt = create_assistant_prompt(assistant_info)

    # Get greeting message from config or use default
    greeting = assistant_info.get('greeting_message', f"Thank you for calling {clinic_name}. This is the front desk. How can I help you today?")

    # Create system instructions for OpenAI
    system_instructions = f"""You are the front desk receptionist answering an incoming phone call for {clinic_name}.

{system_prompt}

CRITICAL FIRST ACTION:
- As soon as the call connects, immediately speak this greeting: "{greeting}"
- Do NOT wait for the caller to speak first
- After greeting, pause briefly to let them respond

Important behavioral guidelines:
- After your greeting, ask for the caller's name and how you can help them
- If they want to schedule an appointment, ask which doctor they prefer and their preferred date/time
- Provide available appointment times based on doctor availability
- Collect necessary information: patient name, reason for visit, preferred doctor, and time
- Confirm all appointment details before ending the call
- Be helpful, professional, and courteous at all times
- Keep responses natural and concise"""

    try:
        # Create and start the OpenAI server for inbound calls
        server = OpenAICallServer(system_instructions, greeting_message=greeting)

        print("Starting OpenAI voice server for INBOUND calls...")

        # Automatically update Twilio webhook
        print("\n🔄 Attempting to auto-update Twilio webhook...")
        update_twilio_webhook(webhook_url)

        print(f"\nServer will run on port {port} (HTTP + WebSocket on same port)")
        print("\nWaiting for incoming calls. Press Ctrl+C to stop.\n")

        # Run the server (this blocks and waits for incoming calls)
        server.run(host='0.0.0.0', port=port)

    except ValueError as e:
        print(f"Error: {e}")
        print("\nPlease ensure the following environment variables are set:")
        print("  TWILIO_ACCOUNT_SID")
        print("  TWILIO_AUTH_TOKEN")
        print("  TWILIO_PHONE_NUMBER")
        print("  OPENAI_API_KEY")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[Inbound call server stopped]\n")

def azure_inbound_mode(assistant_info, webhook_url, port=5001):
    """Handle inbound calls using Azure Voice Live API (front desk mode)"""
    clinic_name = assistant_info.get('clinic_name', 'Allegaro Pediatrics')
    print("\n" + "="*60)
    print(f"{clinic_name.upper()} - FRONT DESK - INBOUND CALLS")
    print("="*60)
    print(f"Webhook URL: {webhook_url}")
    print(f"Local Port: {port}")
    print(f"Mode: Azure Voice Live API (ultra-low latency)")
    print("="*60 + "\n")

    system_prompt = create_assistant_prompt(assistant_info)

    # Get greeting message from config or use default
    greeting = assistant_info.get('greeting_message', f"Thank you for calling {clinic_name}. This is the front desk. How can I help you today?")

    # Create system instructions for Azure
    system_instructions = f"""You are the front desk receptionist answering an incoming phone call for {clinic_name}.

{system_prompt}

CRITICAL FIRST ACTION:
- As soon as the call connects, immediately speak this greeting: "{greeting}"
- Do NOT wait for the caller to speak first
- After greeting, pause briefly to let them respond

Important behavioral guidelines:
- After your greeting, ask for the caller's name and how you can help them
- If they want to schedule an appointment, ask which doctor they prefer and their preferred date/time
- Provide available appointment times based on doctor availability
- Collect necessary information: patient name, reason for visit, preferred doctor, and time
- Confirm all appointment details before ending the call
- Be helpful, professional, and courteous at all times
- Keep responses natural and concise"""

    try:
        # Create and start the azure server for inbound calls
        server = AzureCallServer(system_instructions, greeting_message=greeting)

        print("Starting Azure voice server for INBOUND calls...")

        # Automatically update Twilio webhook
        print("\n🔄 Attempting to auto-update Twilio webhook...")
        update_twilio_webhook(webhook_url)

        print(f"\nServer will run on port {port} (HTTP + WebSocket on same port)")
        print("\nWaiting for incoming calls. Press Ctrl+C to stop.\n")

        # Run the server (this blocks and waits for incoming calls)
        server.run(host='0.0.0.0', port=port)

    except ValueError as e:
        print(f"Error: {e}")
        print("\nPlease ensure the following environment variables are set:")
        print("  TWILIO_ACCOUNT_SID")
        print("  TWILIO_AUTH_TOKEN")
        print("  TWILIO_PHONE_NUMBER")
        print("  AZURE_VOICELIVE_API_KEY")
        print("  AZURE_VOICELIVE_ENDPOINT")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[Inbound call server stopped]\n")

def main():
    parser = argparse.ArgumentParser(description='AI Agent for Doctor Appointment Booking and Personal Assistant')
    parser.add_argument('--mode', choices=['openai', 'azure', 'openai-inbound', 'azure-inbound'],
                        default='openai',
                        help='Mode to run the agent (default: openai)')
    parser.add_argument('--config', default='patient_info.json',
                        help='Path to config file (patient_info.json for outbound, assistant_info.json for inbound)')
    parser.add_argument('--phone', help='Doctor office phone number for outbound calls (E.164 format, e.g., +1234567890)')
    parser.add_argument('--webhook', help='Public webhook URL for Twilio callbacks')
    parser.add_argument('--port', type=int, default=5001, help='Port for webhook server (default: 5001)')

    args = parser.parse_args()

    # Determine if this is inbound or outbound mode
    is_inbound = 'inbound' in args.mode

    if is_inbound:
        # Load assistant configuration for inbound calls
        try:
            with open('assistant_info.json', 'r') as f:
                assistant_info = json.load(f)
        except FileNotFoundError:
            print("Error: assistant_info.json not found!")
            print("Please create assistant_info.json for inbound call configuration.")
            sys.exit(1)

        clinic_name = assistant_info.get('clinic_name', 'Allegaro Pediatrics')
        print(f"\nLoaded front desk configuration for: {clinic_name}")

        if not args.webhook:
            print("Error: --webhook is required for inbound mode")
            print("Example: python3 agent.py --mode openai-inbound --webhook https://your-domain.ngrok.io")
            sys.exit(1)

        if args.mode == 'openai-inbound':
            openai_inbound_mode(assistant_info, args.webhook, args.port)
        elif args.mode == 'azure-inbound':
            azure_inbound_mode(assistant_info, args.webhook, args.port)
    else:
        # Load patient information for outbound calls
        patient_info = load_patient_info(args.config)
        print(f"\nLoaded patient information for: {patient_info['name']}")

        if args.mode == 'openai':
            if not args.phone or not args.webhook:
                print("Error: --phone and --webhook are required for openai mode")
                print("Example: python3 agent.py --mode openai --phone +1234567890 --webhook https://your-domain.ngrok.io")
                sys.exit(1)
            openai_phone_mode(patient_info, args.phone, args.webhook, args.port)
        elif args.mode == 'azure':
            if not args.phone or not args.webhook:
                print("Error: --phone and --webhook are required for azure mode")
                print("Example: python3 agent.py --mode azure --phone +1234567890 --webhook https://your-domain.ngrok.io")
                sys.exit(1)
            azure_phone_mode(patient_info, args.phone, args.webhook, args.port)

if __name__ == "__main__":
    main()
