# Helpdesk Working Time Configuration

## Overview
The Enhanced Helpdesk module now includes configurable working time settings that are specifically designed for helpdesk tickets. This feature allows you to:

- Define working hours for different days of the week
- Calculate SLA deadlines based only on business hours
- Track time spent on tickets during working hours only
- Get accurate SLA breach notifications that consider working time

## Configuration

### 1. Access Working Time Configuration
Navigate to: **Helpdesk → Configuration → Working Time**

### 2. Create Working Time Configurations
You can create multiple working time configurations for different scenarios:

#### Standard Business Hours (Default)
- Monday to Friday: 8:00 AM - 5:00 PM
- Saturday & Sunday: No working hours

#### Extended Support Hours
- Monday to Friday: 7:00 AM - 7:00 PM  
- Saturday: 9:00 AM - 1:00 PM
- Sunday: No working hours

### 3. Working Time Fields
- **Configuration Name**: Descriptive name for the configuration
- **Day of Week**: Select the day (Monday = 0, Sunday = 6)
- **Work from**: Start hour in 24-hour format (e.g., 8.0 for 8:00 AM)
- **Work to**: End hour in 24-hour format (e.g., 17.0 for 5:00 PM)
- **Active**: Enable/disable this configuration
- **Company**: Company this configuration belongs to

## Using Working Time with Helpdesk Tickets

### 1. Automatic Assignment
When a new helpdesk ticket is created, the system automatically assigns the first available working time configuration.

### 2. Manual Configuration
You can manually set working time configuration for tickets:
- Open a helpdesk ticket
- Go to the **SLA & Working Time** tab
- Select the desired **Working Time Configuration**
- Click **Configure Working Time** to change settings

### 3. Bulk Configuration
To apply working time configuration to multiple tickets:
1. Go to **Helpdesk → Tickets**
2. Select multiple tickets from the list
3. Click **Actions → Apply Working Time Configuration**
4. Choose the configuration and whether to recalculate SLA deadlines
5. Click **Apply Configuration**

## New Features and Fields

### 1. SLA & Working Time Tab
Each helpdesk ticket now has a dedicated tab showing:
- **Working Time Configuration**: Currently assigned configuration
- **Business Hours Spent**: Time spent on ticket during working hours only
- **SLA Remaining Hours**: Remaining SLA time considering working hours
- **SLA Breached**: Whether SLA has been breached
- **SLA Breach Time**: When the breach occurred

### 2. Enhanced Ticket List View
The ticket list now shows additional columns (optional):
- **Business Hours**: Time spent in business hours
- **SLA Remaining**: Remaining SLA hours
- **Working Time**: Assigned working time configuration

### 3. Intelligent SLA Calculations
- **SLA Deadlines**: Calculated based on working hours only
- **Business Hours Tracking**: Only counts time during configured working hours
- **Smart Breach Detection**: SLA breaches only occur during working hours

### 4. Enhanced SLA Breach Notifications
When an SLA breach occurs:
- Shows how many business hours the ticket is overdue
- Only triggers during working hours
- Provides detailed breach information in ticket messages

## Server Action
A server action is available in the ticket list view:
- **"Apply Working Time Configuration"**: Bulk assign working time to selected tickets

## Cron Job
The existing SLA breach checking cron job now considers working time:
- Runs every 5 minutes
- Only marks tickets as breached during working hours
- Calculates overdue time in business hours

## Technical Implementation

### Models
- `helpdesk.working.time`: Stores working time configurations
- `helpdesk.working.time.wizard`: Wizard for bulk configuration

### Key Methods
- `_calculate_business_hours()`: Calculates business hours between two dates
- `_calculate_sla_deadline_with_working_time()`: Calculates SLA deadline considering working time
- `_recalculate_sla_with_working_time()`: Recalculates existing SLA deadlines
- `_check_sla_breaches()`: Enhanced SLA breach checking with working time

### Computed Fields
- `business_hours_spent`: Automatically calculated business hours
- `sla_remaining_hours`: Remaining SLA time in business hours
- `is_on_hold`: Whether ticket is on hold (affects time calculation)

## Benefits

1. **Accurate SLA Management**: SLA calculations now reflect actual working hours
2. **Better Resource Planning**: Track time spent during business hours only
3. **Flexible Configuration**: Different working time configurations for different scenarios
4. **Automated Processing**: Intelligent SLA breach detection during working hours
5. **Bulk Operations**: Easy configuration of multiple tickets at once

## Usage Examples

### Example 1: Standard Business Support
- Configure Monday-Friday 9 AM - 6 PM
- Weekend tickets don't count against SLA until Monday
- SLA timers pause outside business hours

### Example 2: Extended Support
- Configure Monday-Friday 7 AM - 7 PM + Saturday 9 AM - 1 PM
- Provides weekend support with limited hours
- SLA calculations include Saturday morning hours

### Example 3: Global Support
- Create multiple configurations for different time zones
- Assign appropriate configuration based on customer location
- Ensure SLA calculations match customer expectations

This working time configuration system ensures that your helpdesk SLA management accurately reflects your actual business operations and provides fair, realistic expectations for both staff and customers.
