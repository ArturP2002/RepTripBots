"""English texts for agents (Telegram / WhatsApp)."""

TEXTS = {
    "agent_welcome": (
        "Hi{name_part} 👋\n\n"
        "{rep_name} from {provider} will be in {city} on {dates}\n"
        "and would be happy to meet local education agents.\n\n"
        "Would you like to arrange a meeting?"
    ),
    "btn_yes": "Yes, I'd like to meet",
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
}
