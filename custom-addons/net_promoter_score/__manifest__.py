{
    "name": "Net Promoter Score (NPS) for Survey",
    "version": "1.0",
    "category": "Survey",
    "summary": "Custom Net Promoter Score (NPS) module integrated with Survey",
    "author": "ictpack Solution",
    "depends": ["survey", "web", "base"], 
    "data": [
    "security/ir.model.access.csv",
    "views/nps_actions.xml", 
    "views/nps_menu.xml",
    "views/nps_list_view.xml",
    "views/nps_dashboard_menu.xml",
    "views/portal/feedback_form_template.xml",
    
    #Email Template for customer survey
    'data/nps_send_feedback_email.xml',
    'views/email_template/customer_survey_email_template.xml',
],

    "assets": {
        "web.assets_backend": [
            "net_promoter_score/static/src/css/custom.css",
        
        'net_promoter_score/static/src/components/**/*.js',
            'net_promoter_score/static/src/components/**/*.xml',
            'net_promoter_score/static/src/components/**/*.scss',
           
        ],
        "web.assets_frontend": [
            "net_promoter_score/static/src/css/custom.css",
        ],
    },
    "installable": True,
}
