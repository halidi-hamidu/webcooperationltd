# SMS NOTIFICATION

This is the README file for the `sms_notification` module. 
```commandline
 This module sends SMS notifications for recurring invoices 
    - It sends 15 days before next invoice date reminder to clients for monthly service payments.
    - Sends the sms reminder on the last day of the last month of the service.
    - Sends another reminder 7 days after the last month of the service.
    - Sends sms reminders for overdue invoices to customers.
```

## Installation

To install this module, simply download it and add it to your Odoo addons directory. Then, restart the Odoo server and go to the Apps menu to install the module.

## Configuration

After installing the module, you may need to configure certain settings to make it work properly.
```commandline
1. Go to Settings 
2. Select SMS Notification Settings Menu
3. Fill all the required Fields 
4. Save to continue
```

## Usage

Once the module is installed and configured, you can start using it.
```commandline
You can either run it manually in scheduled actions (Send Invoice Reminders) or
using a button(Send SMS [Service Reminder]) in invoice form 
```

If you need help with this module or have questions, please provide contact [support@ictpack.com](support@ictpack.com)
