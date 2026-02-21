#!/usr/bin/env python3
"""
Automated Availability Checker
Checks restaurant availability and sends email notifications.
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.resy_client_factory import ResyClientFactory
from utils.email_sender import EmailSender
from config.settings import Settings


def check_availability(restaurant_slug, date, party_size=2, location='ny'):
    """
    Check availability at a restaurant and send email if found.

    Args:
        restaurant_slug: Restaurant slug (e.g., 'temple-court')
        date: Date in YYYY-MM-DD format
        party_size: Number of guests
        location: City code (default: 'ny')

    Returns:
        List of available slots
    """
    print(f"\n{'='*60}")
    print(f"Checking: {restaurant_slug} on {date} for {party_size}")
    print(f"{'='*60}\n")

    try:
        # Create Resy client
        client = ResyClientFactory.create_client()

        # Get venue info
        venue = client.get_venue_by_slug(restaurant_slug, location)
        if not venue:
            print(f"✗ Could not find restaurant: {restaurant_slug}")
            return []

        print(f"✓ Found: {venue['name']}")

        # Check availability
        slots = client.get_availability(venue['id'], date, party_size)

        if slots:
            print(f"✓ Found {len(slots)} available slots!")

            # Send email notification
            if Settings.has_email_configured():
                email_sender = EmailSender()

                # Format slots list
                slots_text = "\n".join([
                    f"  • {slot['time']} - {slot.get('table_name', 'Standard')}"
                    for slot in slots[:10]
                ])

                message = f"""# 🎉 Availability Found!

**Restaurant:** {venue['name']}
**Date:** {date}
**Party Size:** {party_size}

## Available Times:
{slots_text}

---
*Automated check at {datetime.now().strftime('%Y-%m-%d %I:%M %p')}*
"""

                email_sender.send(
                    to_email=Settings.EMAIL_TO,
                    subject=f"🎉 Availability at {venue['name']} on {date}",
                    content=message,
                    content_type="markdown"
                )
                print("✓ Email notification sent!")
        else:
            print("✗ No availability found")

        # Cleanup if browser client
        if hasattr(client, '_cleanup'):
            client._cleanup()

        return slots

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return []


def main():
    """Check availability for configured restaurants."""

    # Define restaurants to check
    # Format: (slug, date, party_size, location)
    restaurants_to_check = [
        ('temple-court', '2026-02-25', 2, 'ny'),
        # Add more restaurants here:
        # ('carbone', '2026-02-26', 2, 'ny'),
        # ('don-angie', '2026-02-27', 4, 'ny'),
    ]

    print("\n" + "="*60)
    print("AUTOMATED AVAILABILITY CHECK")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    print("="*60)

    results = []
    for restaurant_slug, date, party_size, location in restaurants_to_check:
        slots = check_availability(restaurant_slug, date, party_size, location)
        if slots:
            results.append({
                'restaurant': restaurant_slug,
                'date': date,
                'slots': len(slots)
            })

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    if results:
        print(f"✓ Found availability at {len(results)} restaurant(s):")
        for r in results:
            print(f"  • {r['restaurant']} on {r['date']}: {r['slots']} slots")
    else:
        print("✗ No availability found at any restaurants")
    print()


if __name__ == "__main__":
    main()
