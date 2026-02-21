#!/usr/bin/env python3
"""
Reservation Sniper
Continuously monitors for availability and auto-books when found.

⚠️  WARNING: This will automatically make REAL reservations!
Use with caution and only for restaurants you genuinely want to book.
"""

import sys
import os
import time
from datetime import datetime, timedelta
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.resy_client_factory import ResyClientFactory
from utils.reservation_store import ReservationStore
from utils.email_sender import EmailSender
from config.settings import Settings


class ReservationSniper:
    """Monitors for availability and auto-books reservations."""

    def __init__(self, config_file='sniper_config.json'):
        """
        Initialize sniper with configuration.

        Args:
            config_file: Path to JSON config file with target reservations
        """
        self.config_file = config_file
        self.client = None
        self.store = ReservationStore()
        self.email_sender = EmailSender() if Settings.has_email_configured() else None
        self.already_booked = set()  # Track what we've already booked

    def load_config(self):
        """
        Load configuration from JSON file.

        Config format:
        {
            "targets": [
                {
                    "restaurant": "temple-court",
                    "location": "ny",
                    "date": "2026-02-25",
                    "party_size": 2,
                    "preferred_times": ["18:00", "18:30", "19:00"],
                    "auto_book": false,
                    "priority": "high"
                }
            ],
            "check_interval_seconds": 300,
            "max_checks_per_session": 100,
            "stop_when_found": true
        }
        """
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config',
            self.config_file
        )

        if not os.path.exists(config_path):
            # Create default config
            default_config = {
                "targets": [
                    {
                        "restaurant": "temple-court",
                        "location": "ny",
                        "date": "2026-02-25",
                        "party_size": 2,
                        "preferred_times": ["18:00", "19:00"],
                        "auto_book": False,
                        "priority": "high"
                    }
                ],
                "check_interval_seconds": 300,  # 5 minutes
                "max_checks_per_session": 100,
                "stop_when_found": True
            }

            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)

            print(f"Created default config at: {config_path}")
            print("Edit this file to configure your target reservations")

        with open(config_path, 'r') as f:
            return json.load(f)

    def check_target(self, target):
        """
        Check availability for a single target.

        Args:
            target: Target configuration dict

        Returns:
            List of matching available slots
        """
        restaurant = target['restaurant']
        location = target.get('location', 'ny')
        date = target['date']
        party_size = target['party_size']
        preferred_times = target.get('preferred_times', [])

        print(f"\n  Checking: {restaurant} on {date} for {party_size}")

        try:
            # Get venue
            venue = self.client.get_venue_by_slug(restaurant, location)
            if not venue:
                print(f"    ✗ Could not find restaurant")
                return []

            # Check availability
            slots = self.client.get_availability(venue['id'], date, party_size)

            if not slots:
                print(f"    ✗ No availability")
                return []

            # Filter by preferred times if specified
            if preferred_times:
                matching_slots = []
                for slot in slots:
                    slot_time = slot.get('time', '')
                    # Check if slot time matches any preferred time
                    for pref_time in preferred_times:
                        if pref_time in slot_time or slot_time.startswith(pref_time):
                            matching_slots.append(slot)
                            break

                if matching_slots:
                    print(f"    ✓ Found {len(matching_slots)} matching slot(s)!")
                    for slot in matching_slots:
                        print(f"      • {slot['time']}")
                else:
                    print(f"    ⚠️  Found {len(slots)} slots but none match preferred times")

                return matching_slots
            else:
                print(f"    ✓ Found {len(slots)} slot(s)")
                return slots

        except Exception as e:
            print(f"    ✗ Error: {e}")
            return []

    def book_slot(self, target, slot):
        """
        Book a reservation slot.

        Args:
            target: Target configuration dict
            slot: Slot to book

        Returns:
            bool: True if booking succeeded
        """
        restaurant = target['restaurant']
        date = target['date']
        party_size = target['party_size']

        print(f"\n    🎫 BOOKING: {restaurant} on {date} at {slot['time']}")
        print(f"       ⚠️  This will make a REAL reservation!")

        try:
            result = self.client.make_reservation(
                config_id=slot['config_id'],
                date=date,
                party_size=party_size
            )

            if result.get('success'):
                print(f"       ✅ BOOKING SUCCESSFUL!")
                print(f"          Confirmation: {result.get('reservation_id')}")

                # Save to database
                self.store.add_reservation({
                    'platform': 'resy',
                    'restaurant_name': restaurant,
                    'date': date,
                    'time': slot['time'],
                    'party_size': party_size,
                    'confirmation_number': result.get('reservation_id'),
                    'confirmation_token': result.get('confirmation_token'),
                    'status': 'confirmed'
                })

                # Send email notification
                if self.email_sender:
                    self.email_sender.send(
                        to_email=Settings.EMAIL_TO,
                        subject=f"🎉 AUTO-BOOKED: {restaurant} on {date}",
                        content=f"""# 🎉 Reservation Auto-Booked!

**Restaurant:** {restaurant}
**Date:** {date}
**Time:** {slot['time']}
**Party Size:** {party_size}
**Confirmation:** {result.get('reservation_id')}

---
*Booked by Reservation Sniper at {datetime.now().strftime('%Y-%m-%d %I:%M %p')}*
""",
                        content_type="markdown"
                    )

                return True
            else:
                print(f"       ✗ Booking failed: {result.get('error')}")
                return False

        except Exception as e:
            print(f"       ✗ Booking error: {e}")
            return False

    def run(self):
        """Run the sniper in continuous monitoring mode."""
        print("\n" + "="*60)
        print("RESERVATION SNIPER")
        print("="*60)
        print("⚠️  WARNING: This will AUTO-BOOK reservations!")
        print("Make sure auto_book is only enabled for restaurants you want.")
        print("="*60 + "\n")

        # Load config
        config = self.load_config()
        targets = config['targets']
        check_interval = config.get('check_interval_seconds', 300)
        max_checks = config.get('max_checks_per_session', 100)
        stop_when_found = config.get('stop_when_found', True)

        print(f"Loaded {len(targets)} target(s)")
        print(f"Check interval: {check_interval} seconds")
        print(f"Max checks: {max_checks}")
        print()

        # Create client
        self.client = ResyClientFactory.create_client()

        check_count = 0
        found_count = 0

        try:
            while check_count < max_checks:
                check_count += 1
                print(f"\n{'='*60}")
                print(f"CHECK #{check_count} - {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
                print(f"{'='*60}")

                for target in targets:
                    restaurant = target['restaurant']
                    date = target['date']
                    auto_book = target.get('auto_book', False)

                    # Skip if already booked
                    booking_key = f"{restaurant}-{date}"
                    if booking_key in self.already_booked:
                        print(f"\n  ✓ {restaurant} already booked, skipping")
                        continue

                    # Check for availability
                    slots = self.check_target(target)

                    if slots:
                        found_count += 1

                        if auto_book:
                            # Auto-book first matching slot
                            slot = slots[0]
                            success = self.book_slot(target, slot)

                            if success:
                                self.already_booked.add(booking_key)

                                if stop_when_found:
                                    print(f"\n✓ Booking complete. Stopping as configured.")
                                    return
                        else:
                            # Just notify, don't book
                            print(f"    💡 auto_book=false, skipping booking")

                            if self.email_sender:
                                self.email_sender.send(
                                    to_email=Settings.EMAIL_TO,
                                    subject=f"🔔 Availability Found: {restaurant}",
                                    content=f"""# 🔔 Availability Alert

**Restaurant:** {restaurant}
**Date:** {date}
**Available Slots:** {len(slots)}

Times: {', '.join([s['time'] for s in slots[:5]])}

---
*Found by Reservation Sniper at {datetime.now().strftime('%Y-%m-%d %I:%M %p')}*
*auto_book is disabled for this target*
""",
                                    content_type="markdown"
                                )

                # Wait before next check
                if check_count < max_checks:
                    print(f"\n⏳ Waiting {check_interval} seconds until next check...")
                    time.sleep(check_interval)

            print(f"\n✓ Completed {check_count} checks. Found availability {found_count} times.")

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Stopped by user. Completed {check_count} checks.")
        finally:
            # Cleanup
            if hasattr(self.client, '_cleanup'):
                self.client._cleanup()


def main():
    """Run the reservation sniper."""
    sniper = ReservationSniper()
    sniper.run()


if __name__ == "__main__":
    main()
