"""English texts for owners and agents (Telegram / WhatsApp)."""

TEXTS = {
    "agent_welcome": (
        "Hi{name_part} 👋\n\n"
        "{rep_name} from {provider} will be in {city} on {dates}\n"
        "and would be happy to meet local education agents.\n\n"
        "Would you like to arrange a meeting?"
    ),
    "btn_yes": "Yes, let's meet",
    "btn_no": "No, thanks",
    "agent_declined_invite": "Thank you for letting us know. Have a great day!",
    "register_ask_name": "Please share your full name:",
    "register_ask_agency": "Your agency name:",
    "register_ask_email": "Your email:",
    "register_ask_phone": "Your phone number:",
    "register_ask_office": "Your office address (for the in-person meeting):",
    "register_done": "Thanks, {name}! You're registered.",
    "known_agent": "Welcome back, {name}! We still have your profile on file.",
    "ask_format": "How would you prefer to meet?",
    "btn_in_person": "In person",
    "btn_online": "Online",
    "pick_slot": "Please choose a preferred time:",
    "pick_date": "Please choose a date:",
    "pick_time": "Please choose a time for {date}:",
    "btn_back_dates": "← Back to dates",
    "btn_more_times": "More times →",
    "slot_busy_alert": "This time is not available.",
    "day_busy_alert": "This day has no free slots.",
    "no_slots": "Sorry, there are no available slots right now. Please try later.",
    "request_sent": (
        "Thanks! We've sent your meeting request for {when}.\n"
        "You'll get a confirmation once it's approved."
    ),
    "confirmed": (
        "Confirmed ✅\n\n"
        "Meeting with {rep_name} from {provider}\n"
        "{when}\n"
        "{format_line}\n"
        "{location_line}"
    ),
    "declined": (
        "Unfortunately, the representative can't confirm a meeting "
        "at the requested time. Thank you for your interest."
    ),
    "suggest_received": (
        "{rep_name} suggested another time: {when}\n"
        "Does this work for you?"
    ),
    "btn_suggest_yes": "Yes",
    "btn_choose_another": "Choose another time",
    "cancelled": "Your meeting has been cancelled. The time slot is free again.",
    "btn_cancel_meeting": "Cancel meeting",
    "error_generic": "Something went wrong. Please try again later.",
    "trip_not_found": "This invitation link is invalid or expired.",
    "non_owner_hint": (
        "To arrange a meeting, please open the invitation link from your email "
        "or contact the RepTrip organiser."
    ),
    "go_page_title": "RepTrip — arrange a meeting",
    "go_page_body": "Continue in your preferred messenger:",
    "btn_continue_tg": "Continue in Telegram",
    "btn_continue_wa": "Continue in WhatsApp",

    # Owner messages and buttons.
    'owner_only': 'This command is only available to the bot owner.',
    'owner_welcome': 'RepTrip — owner panel.\n\nCommands:\n/new_trip — create a trip\n/trips — list active trips\n/help — help',
    'help_owner': 'Create a trip with /new_trip, get invitation links for agents, and email them manually.\nMeeting requests appear here: Confirm / Suggest another time / Decline.\n\nA calendar event is created only after an agent chooses a time and you press Confirm.',
    'trip_create_start': 'Create a trip. Enter the organisation name (educational institution):',
    'trip_ask_rep_name': 'Representative name:',
    'trip_ask_rep_email': 'Representative email:',
    'trip_ask_city': 'Trip city (e.g. Almaty / Tashkent):',
    'trip_ask_country': 'Country: choose a button or enter Kazakhstan / Uzbekistan.',
    'trip_ask_start_date': 'Start date (DD.MM.YYYY):',
    'trip_ask_end_date': 'End date (DD.MM.YYYY):',
    'trip_ask_hours': 'Meeting hours in HH:MM-HH:MM format (e.g. 10:00-18:00).\nThe same hours apply to every day of the trip.',
    'trip_ask_format': 'Meeting format:',
    'trip_ask_location_mode': 'Where will in-person meetings take place?',
    'trip_ask_common_location': 'Meeting address (where agents will come):',
    'trip_ask_online_link': 'Permanent online meeting link:',
    'trip_invalid_date': 'Could not read the date. Format: DD.MM.YYYY',
    'trip_invalid_hours': 'Invalid time format. Example: 10:00-18:00',
    'trip_created': '✅ Trip created.\n\nID: {trip_id}\n{provider} · {rep_name}\n{city}, {country}\n{start_date} — {end_date}\nTime zone: {timezone}\nFormat: {meeting_format}\n\nMessenger selection page:\n{go_link}\n\nEmail the link to agents manually.\nA Google Calendar event will be created once you confirm an agent’s meeting request.',
    'trips_empty': 'No active trips yet. Create one with /new_trip.',
    'trips_list_item': '#{id} {city} ({country}) {start}–{end} · code={token}',
    'new_meeting_request': '📩 New meeting request\n\n{agent_name}\n{agency}\n{when}\n{meeting_format}\n{location_line}\nTrip: {city} (#{trip_id})',
    'btn_confirm': 'Confirm',
    'btn_suggest': 'Another time',
    'btn_decline': 'Decline',
    'confirm_ok': '✅ Meeting confirmed. The agent has been notified and the event added to Google Calendar.',
    'confirm_busy': '⚠️ This time is already booked in the calendar. No booking was created.\nSuggest another time using the Another time button.',
    'decline_ok': 'Request declined. The agent has been notified.',
    'suggest_ask_slot': 'Choose a new time to suggest to the agent:',
    'suggest_sent': 'The suggested time has been sent to the agent.',
    'suggest_no_slots': 'No available time slots.',
    'cancel_notify_owner': '❌ The agent cancelled the meeting\n{agent_name} · {agency}\n{when}',
    'cancelled_by_owner_flow': 'Operation cancelled.',
    'btn_kz': 'Kazakhstan',
    'btn_uz': 'Uzbekistan',
    'btn_both': 'In person and online',
    'btn_visit_offices': 'I will visit agents',
    'btn_agents_come': 'Agents will come to me',
    'format_in_person': 'In person',
    'format_online': 'Online',
    'format_both': 'In person and online',
}
