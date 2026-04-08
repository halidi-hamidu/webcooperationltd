# SMS Invoice Notifications Module

## Overview

This module provides automated SMS notifications for invoice reminders using Odoo's built-in `mass_mailing_sms` module and `sms_infobip` provider for delivery.

## Features

### Automated Invoice Reminders
- **New Registration**: SMS sent when new vehicles are registered
- **30 Days Before**: Reminder 30 days before invoice due date
- **15 Days Before**: Reminder 15 days before invoice due date  
- **Due Date**: Reminder on the invoice due date
- **7 Days After**: Follow-up 7 days after due date
- **Above 7 Days**: Escalation for invoices overdue by more than 7 days

### Integration with Mass Mailing SMS
- Uses Odoo's `mailing.mailing` model for SMS campaigns
- Full SMS Marketing features (analytics, tracking, reporting)
- Automatic contact management via `mailing.contact`
- Infobip integration for reliable delivery
- SMS delivery status tracking (sent, delivered, failed)
- Future: A/B testing, segmentation, and advanced analytics

## Architecture

### Models Used

1. **mailing.mailing** (from mass_mailing_sms)
   - Stores SMS campaign/message details
   - Handles sending via Infobip provider
   - Tracks delivery status

2. **mailing.contact** (from mass_mailing_sms)
   - Stores customer contact information
   - Linked to `res.partner`

3. **account.move** (extended)
   - Tracks SMS limits per reminder type
   - Generates SMS mailings via cron job

4. **sale.order** (extended)
   - Generates registration SMS for new vehicles

## Configuration

### 1. Install Dependencies
```bash
# Ensure these modules are installed:
- sms
- sms_infobip  
- mass_mailing_sms
- custom_ictpack
```

### 2. Configure Infobip Provider
1. Go to Settings > General Settings > Integrations
2. Locate "Infobip SMS" section
3. Enter your Infobip credentials:
   - API Base URL
   - API Key
   - Sender Name

### 3. Enable Scheduled Actions
Go to Settings > Technical > Automation > Scheduled Actions:

- **Queue SMS Notifications (LATRA-VTS)**
  - Interval: 1 hour (recommended)
  - Generates SMS mailings for invoices based on due dates
  - Model: `account.move`
  - Code: `model.queue_sms_notification()`

### 4. SMS Templates
Located in `data/sms_templates.xml`:
- New Registration
- 30 Days Before Reminder
- 15 Days Before Reminder
- Due Date Reminder
- 7 Days After Reminder
- Above 7 Days After Reminder

## Usage

### Automated Flow
1. Cron job runs and checks all draft invoices
2. For each invoice, checks if reminders are due based on dates
3. Creates `mailing.mailing` record with SMS content
4. SMS is queued for sending via mass_mailing_sms
5. Infobip sends SMS and reports delivery status
6. Status tracked in SMS Marketing app

### Manual Registration SMS
From Sale Order:
1. Select Registered Cars (atras projects)
2. Click "GENERATE REGISTRATION SMS" button
3. SMS mailing created and queued for sending

### View SMS History
- On Customer form: SMS smart button shows SMS count
- Click to view all SMS mailings for that customer
- Access full SMS Marketing app for analytics

## Technical Details

### SMS Mailing Creation
```python
def create_sms_mailing(self, obj, message, template, sms_type):
    # Creates mailing.contact if not exists
    # Creates mailing.mailing record with:
    # - Subject: SMS type + customer + invoice
    # - Body: Rendered template message  
    # - Type: SMS
    # - State: draft (ready to send)
```

### SMS Limits
Each invoice tracks limits to prevent duplicate sends:
- `new_registration_sms_limit`
- `thirty_days_before_sms_limit`
- `fifteen_days_sms_limit`
- `due_day_sms_limit`
- `seven_days_sms_limit`
- `above_seven_days_sms_limit`

## Future Enhancements

### Infobip Advanced Features
- Real-time delivery reports
- SMS open/read tracking
- Link click tracking
- Reply handling

### Mass Mailing SMS Features
- A/B testing for message optimization
- Advanced segmentation
- Campaign performance analytics
- Unsubscribe management
- Bulk sending optimization

## Monitoring

### Check SMS Status
1. Go to SMS Marketing app
2. View campaigns filtered by "SMS" type
3. Check delivery statistics:
   - Sent count
   - Delivered count
   - Failed count
   - Error details

### Logs
- SMS sending: Check `mailing.mailing` records
- Delivery status: Check `mailing.trace` records
- Errors: Check Odoo logs and Infobip dashboard

## Troubleshooting

### SMS Not Sending
1. Check Infobip credentials in Settings
2. Verify customer has valid mobile/phone number
3. Check SMS Marketing app for error messages
4. Verify `mailing.contact` created for customer

### Duplicate SMS
- Check invoice SMS limit fields
- Verify cron job not running too frequently
- Reset limits if needed via invoice SMS Info tab

### No SMS History
- Ensure `mailing.contact` has `partner_id` set
- Check `mailing.mailing` records exist
- Verify SMS Marketing module is installed

## Development

### Add New SMS Type
1. Add template in `data/sms_templates.xml`
2. Add limit field in `account_move` model
3. Add condition in `queue_sms_notification()` method
4. Update `check_validity()` method with new date logic

### Custom SMS Content
1. Modify template in SMS templates
2. Use Jinja2 syntax for dynamic content
3. Access invoice fields via `object` variable
4. Test rendering via `_render_template()` method

## Dependencies
- `sms`: Core SMS functionality
- `sms_infobip`: Infobip provider integration
- `mass_mailing_sms`: SMS Marketing features
- `account`: Invoice management
- `sale`: Sales order integration
- `custom_ictpack`: Business line customizations

## Support
For questions or issues with this module, contact support@ictpack.com
