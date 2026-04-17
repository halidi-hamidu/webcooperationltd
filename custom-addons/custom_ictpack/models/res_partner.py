from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    vrn = fields.Char(string='VRN', default=False, copy=False)

    # Selcom Till Alias fields
    till_alias = fields.Char(string='Selcom Till Alias', readonly=True, copy=False)
    till_alias_synced = fields.Boolean(default=False, copy=False)

    def get_config_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)

    def action_create_till_alias(self):
        self.ensure_one()
        api_url = self.get_config_param('custom_ictpack.cips_api_url')
        api_token = self.get_config_param('custom_ictpack.cips_api_token')

        if not api_url or not api_token:
            raise UserError(_(
                "CIPS API URL and Token must be configured under "
                "Company Settings > CIPS / Selcom."
            ))

        if self.till_alias and self.till_alias_synced:
            raise UserError(_(
                "A Till Alias (%s) already exists for this customer."
            ) % self.till_alias)

        # Use the Odoo database ID as customer_id — always unique and stable.
        # This value is embedded in every Selcom callback so CIPS can route
        # payments back to the correct customer.
        payload = {
            "name": self.name,
            "customer_id": str(self.id),
        }

        try:
            response = requests.post(
                "{}/api/payments/till-alias/".format(api_url.rstrip('/')),
                json=payload,
                headers={
                    "X-API-Key": "{}".format(api_token),
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            raise UserError(_("CIPS API request timed out. Please try again."))
        except requests.exceptions.ConnectionError:
            raise UserError(_("Could not connect to the CIPS API. Check the API URL in company settings."))
        except requests.exceptions.HTTPError as e:
            raise UserError(_("CIPS API returned an error: %s") % str(e))
        except requests.exceptions.RequestException as e:
            raise UserError(_("CIPS API request failed: %s") % str(e))

        if data.get("status") == "success":
            result = data["data"]
            self.write({
                "till_alias": result["till_alias"],
                "till_alias_synced": True,
            })
            _logger.info(
                "Till alias %s assigned to partner id=%s (%s)",
                result["till_alias"], self.id, self.name,
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Till Alias Created'),
                    'message': _('Till Alias %s has been assigned to %s.') % (
                        result["till_alias"], self.name
                    ),
                    'type': 'success',
                    'sticky': False,
                },
            }
        else:
            raise UserError(_("CIPS error: %s") % data.get("message", "Unknown error"))

