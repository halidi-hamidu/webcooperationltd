/* @odoo-module */

import { patch } from 'web.utils';

import { Message } from "@mail/components/message/message";
const session = require("web.session");
const components = { Message };

patch(components.Message.prototype, 'sh_backmate_theme_adv/static/src/components/message/message.js', {


    get isLoginUser(){
    	if (this.messageView && session.partner_id == this.messageView.message.author.id){
    		return true
    	}else{
    		return false
    	}
    	 
    }
});