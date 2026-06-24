def get_team_partner_ids(env, notification_type_key):
    """
    Returns partner IDs of all users (leaders + members) in teams that are
    subscribed to the given notification type key.

    Args:
        env: Odoo environment object (self.env)
        notification_type_key: The key of the VtsNotificationType record
                               (e.g., 'job_card_submitted', 'job_card_approved')

    Returns:
        List of res.partner IDs to notify, deduplicated.
    """
    notification_type = env['vts.notification.type'].search(
        [('key', '=', notification_type_key)], limit=1
    )
    if not notification_type:
        return []

    teams = env['vts.operation.team'].search(
        [('notification_type_ids', 'in', notification_type.id)]
    )

    user_ids = set()
    for team in teams:
        if team.user_id:
            user_ids.add(team.user_id.id)
        user_ids.update(team.member_ids.ids)

    if not user_ids:
        return []

    users = env['res.users'].browse(list(user_ids))
    return [user.partner_id.id for user in users if user.partner_id]


def get_chatter_messages(env, model_name, record_id, message_type='comment', order='date desc', limit=None):
    """
    Generic helper function to retrieve chatter messages for any Odoo model record.

    Args:
        env: Odoo environment object (self.env)
        model_name: String name of the model (e.g., 'vts.job.card', 'project.task')
        record_id: ID of the record to fetch messages for
        message_type: Filter by message type (default: 'comment'). Pass None to skip filter.
        order: Sort order for messages (default: 'date desc')
        limit: Maximum number of messages to return (default: None = all)

    Returns:
        List of message dictionaries with id, sender, message, timestamp, message_type.
    """
    domain = [('res_id', '=', record_id), ('model', '=', model_name)]
    if message_type:
        domain.append(('message_type', '=', message_type))

    messages = env['mail.message'].search(domain, order=order, limit=limit)

    message_data = []
    for message in messages:
        sender_name = 'System'
        if message.author_id:
            sender_name = message.author_id.name

        message_data.append({
            'id': message.id,
            'sender': sender_name,
            'message': message.body,
            'timestamp': message.date,
            'message_type': message.message_type,
        })

    return message_data


def format_response(status, message, data=None):
    return {
        "status": status,
        "message": message,
        "data": data,
    }


def post_chatter_message(env, model_name, record_id, message_body, subject=None, 
                         message_type='comment', subtype_xmlid='mail.mt_comment', 
                         body_is_html=True, **kwargs):
    """
    Generic helper function to post a message to any Odoo model's chatter.
    
    Args:
        env: Odoo environment object (self.env)
        model_name: String name of the model (e.g., 'vts.job.card', 'project.task')
        record_id: ID of the record to post the message to
        message_body: The message content to post
        subject: Optional subject line for the message
        message_type: Type of message (default: 'comment')
        subtype_xmlid: Message subtype (default: 'mail.mt_comment')
        body_is_html: Whether the body contains HTML (default: True)
        **kwargs: Additional parameters to pass to message_post
    
    Returns:
        Dictionary with status, message, and data (message_id or None)
    """
    try:
        # Search for the record
        record = env[model_name].search([('id', '=', record_id)], limit=1)
        
        if not record:
            return format_response('error', f'{model_name} record with ID {record_id} not found.', None)
        
        # Prepare message_post parameters
        post_params = {
            'body': message_body,
            'message_type': message_type,
            'subtype_xmlid': subtype_xmlid,
            'body_is_html': body_is_html,
        }
        
        # Add optional subject if provided
        if subject:
            post_params['subject'] = subject
        
        # Merge any additional kwargs
        post_params.update(kwargs)
        
        # Post the message
        message = record.message_post(**post_params)
        
        return format_response('success', 'Message posted to chatter successfully.', {
            'message_id': message.id if message else None,
            'record_id': record_id,
            # 'model': model_name,
        })
        
    except Exception as e:
        return format_response('error', f'Failed to post message: {str(e)}', None)