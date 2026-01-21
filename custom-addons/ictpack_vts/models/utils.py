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