# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import uuid
import unicodedata
import re

from lxml import etree
from StringIO import StringIO
from openerp import http, _
from openerp.http import request
from odoo.exceptions import UserError
from odoo.tools import ustr

def sanitize_for_xmlid(s):
    """ Transform a string to a name suitable for use in xml_id.
        For example, My new application -> my_new_application.
        It will process string by stripping leading and ending spaces,
        converting unicode chars to ascii, lowering all chars and replacing spaces
        with underscore.
        :param s: str
        :rtype: str
    """
    s = ustr(s)
    uni = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')

    slug_str = re.sub('[\W]', ' ', uni).strip().lower()
    slug_str = re.sub('[-\s]+', '_', slug_str)
    return slug_str


class WebStudioController(http.Controller):

    @http.route('/web_studio/init', type='json', auth='user')
    def studio_init(self, action_id):
        action_model = request.env['ir.actions.act_window'].browse(action_id).res_model
        return {
            'dbuuid': request.env['ir.config_parameter'].get_param('database.uuid'),
            'chatter_allowed': self._is_chatter_allowed(action_model),
            'multi_lang': bool(request.env['res.lang'].search_count([('code', '!=', 'en_US')])),
        }

    @http.route('/web_studio/get_studio_action', type='json', auth='user')
    def get_studio_action(self, action_name, model, view_id=None, view_type=None):
        view_type = 'tree' if view_type == 'list' else view_type  # list is stored as tree in db
        model = request.env['ir.model'].search([('model', '=', model)], limit=1)

        action = None
        if hasattr(self, '_get_studio_action_' + action_name):
            action = getattr(self, '_get_studio_action_' + action_name)(model, view_id=view_id, view_type=view_type)

        return action

    def _get_studio_action_acl(self, model, **kwargs):
        return {
            'name': _('Access Control Lists'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.model.access',
            'views': [[False, 'list'], [False, 'form']],
            'target': 'current',
            'domain': [],
            'context': {'search_default_model_id': model.id},
            'help': """ <p class="oe_view_nocontent_create">
                Click to add a new access control list.
            </p>
            """,
        }

    def _get_studio_action_automations(self, model, **kwargs):
        return {
            'name': _('Automated Actions'),
            'type': 'ir.actions.act_window',
            'res_model': 'base.action.rule',
            'views': [[False, 'list'], [False, 'form']],
            'target': 'current',
            'domain': [],
            'context': {'search_default_model_id': model.id},
            'help': """ <p class="oe_view_nocontent_create">
                Click to add a new automated action.
            </p>
            """,
        }

    def _get_studio_action_filters(self, model, **kwargs):
        return {
            'name': _('Search Filters'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.filters',
            'views': [[False, 'list'], [False, 'form']],
            'target': 'current',
            'domain': [],
            'context': {'search_default_model_id': model.model},  # model_id is a Selection on ir.filters
            'help': """ <p class="oe_view_nocontent_create">
                Click to add a new filter.
            </p>
            """,
        }

    def _get_studio_action_reports(self, model, **kwargs):
        return {
            'name': _('Reports'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.actions.report.xml',
            'views': [[False, 'kanban'], [False, 'form']],
            'target': 'current',
            'domain': [],
            'context': {'search_default_model': model.model},
            'help': """ <p class="oe_view_nocontent_create">
                Click to add a new report.
            </p>
            """,
        }

    def _get_studio_action_translations(self, model, **kwargs):
        """ Open a view for translating the field(s) of the record (model, id). """
        domain = ('|', ('name', '=', model.model), ('name', 'ilike', model.model + ','))

        # search view + its inheritancies
        views = request.env['ir.ui.view'].search([('model', '=', model.model)])
        domain = ('|', '&', ('name', '=', 'ir.ui.view,arch_db'), ('res_id', 'in', views.ids)) + domain

        def make_domain(fld, rec):
            name = "%s,%s" % (fld.model_name, fld.name)
            return ['&', ('res_id', '=', rec.id), ('name', '=', name)]

        def insert_missing(fld, rec):
            if not fld.translate:
                return

            if fld.related:
                try:
                    # traverse related fields up to their data source
                    while fld.related:
                        rec, fld = fld.traverse_related(rec)
                    if rec:
                        domain = ['|'] + domain + make_domain(fld, rec)
                except AccessError:
                    return

            assert fld.translate and rec._name == fld.model_name
            request.env['ir.translation'].insert_missing(fld, rec)

        # insert missing translations of views
        for view in views:
            for name, fld in view._fields.items():
                insert_missing(fld, view)

        # insert missing translations of model, and extend domain for related fields
        record = request.env[model.model].search([], limit=1)
        if record:
            for name, fld in record._fields.items():
                insert_missing(fld, record)

        action = {
            'name': _('Translate view'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.translation',
            'view_mode': 'tree',
            'views': [[request.env.ref('base.view_translation_dialog_tree').id, 'list']],
            'target': 'current',
            'domain': domain,
        }

        return action

    def _create_or_get_module(self, menu_id=None, description=None):
        if menu_id:
            root_menu = request.env['ir.ui.menu'].browse([menu_id])
            model_data = request.env['ir.model.data'].search([['res_id', '=', root_menu.id], ['model', '=', 'ir.ui.menu']])

            if model_data.module.startswith('studio_custom_app_'):
                # this is an application made by Studio, so all modifications
                # should be made in the same module
                module_name = model_data.module
            else:
                # this is a customization for an existing application
                module_name = 'studio_customization_%s' % (model_data.module or 'web_studio')
                module_description = root_menu.name
                is_app = False
        else:
            # this is a totally new application
            module_name = 'studio_custom_app_%s' % sanitize_for_xmlid(description)
            module_description = description
            is_app = True

        if not request.env['ir.module.module'].search_count([['name', '=', module_name]]):
            # need to create a module from scratch
            request.env['ir.module.module'].create({
                'name': module_name,
                'application': is_app,
                'shortdesc': module_description,
                'state': 'installed',
                'imported': True,
            })

        return module_name

    @http.route('/web_studio/create_new_menu', type='json', auth='user')
    def create_new_menu(self, name, model_id, is_app=False, parent_id=None, icon=None, menu_id=None):
        """ Create a new menu @name, linked to a new action associated to the model_id
            @param is_app: if True, create an extra menu (app, without parent)
            @param parent_id: the parent of the new menu.
                To be set if is_app is False.
            @param icon: the icon of the new app, like [icon, icon_color, background_color].
                To be set if is_app is True.
        """
        model_id = request.env['ir.model'].browse(model_id)
        new_action = request.env['ir.actions.act_window'].create({
            'name': name,
            'res_model': model_id.model,
            'help': """
                <p>
                    This is your new action ; by default, it contains a list view and a form view.
                </p>
                <p>
                    You can start customizing these screens by clicking on the Studio icon on the
                    top right corner (you can also customize this help message there).
                </p>
            """,
        })

        module_name = self._create_or_get_module(menu_id, name)

        if is_app:
            # we cannot create a menu without action without the context `full_list`
            new_menu = request.env['ir.ui.menu'].with_context({'ir.ui.menu.full_list': True}).create({
                'name': name,
                'web_icon': ','.join(icon),
                'child_id': [(0, 0, {
                    'name': model_id.name,
                    'action': 'ir.actions.act_window,' + str(new_action.id),
                })]
            })
        else:
            new_menu = request.env['ir.ui.menu'].create({
                'name': name,
                'action': 'ir.actions.act_window,' + str(new_action.id),
                'parent_id': parent_id,
            })

        # Create model data
        self._create_model_data('action_%s' % uuid.uuid4(), 'ir.actions.act_window', new_action.id, module_name)
        self._create_model_data('menu_%s' % uuid.uuid4(), 'ir.ui.menu', new_menu.id, module_name)

        if is_app:
            self._create_model_data('menu_%s' % uuid.uuid4(), 'ir.ui.menu', new_menu.child_id[0].id, module_name)

        return {
            'menu_id': new_menu.id,
            'action_id': new_action.id,
        }

    def _create_model_data(self, name, model, res_id, module):
        model_data = request.env['ir.model.data'].create({
            'name': name,
            'model': model,
            'res_id': res_id,
            'module': module,
        })
        model_data.set_studio_modification()

    @http.route('/web_studio/edit_action', type='json', auth='user')
    def edit_action(self, action_type, action_id, args):

        action_id = request.env[action_type].browse(action_id)
        if action_id:

            if 'groups_id' in args:
                args['groups_id'] = [(6, 0, args['groups_id'])]

            if 'view_mode' in args:
                args['view_mode'] = args['view_mode'].replace('list', 'tree')  # list is stored as tree in db

                # Check that each views in view_mode exists or try to get default
                view_ids = request.env['ir.ui.view'].search([('model', '=', action_id.res_model)])
                view_types = [view_id.type for view_id in view_ids]
                for view_type in args['view_mode'].split(','):
                    if view_type not in view_types:
                        try:
                            request.env[action_id.res_model].fields_view_get(view_type=view_type)
                        except UserError as e:
                            return e.name

                # As view_ids has precedence on view_mode, we need to use them and resequence them
                view_modes = args['view_mode'].split(',')
                if action_id.view_ids:
                    missing_view_modes = [x for x in view_modes if x not in [y.view_mode for y in action_id.view_ids]]
                    for view_mode in missing_view_modes:
                        request.env['ir.actions.act_window.view'].create({'view_mode': view_mode, 'act_window_id': action_id.id})
                for view_id in action_id.view_ids:
                    if view_id.view_mode in view_modes:
                        view_id.sequence = view_modes.index(view_id.view_mode)
                        view_xml_id = request.env['ir.model.data'].search([('model', '=', 'ir.actions.act_window.view'), ('res_id', '=', view_id.id)])
                        if view_xml_id:
                            view_xml_id.set_studio_modification()
                    else:
                        view_id.unlink()

            action_id.write(args)

            if action_id.xml_id:
                self._edit_model_data(action_id.xml_id)

        return True

    @http.route('/web_studio/set_another_view', type='json', auth='user')
    def set_another_view(self, action_id, view_mode, view_id):

        action_id = request.env['ir.actions.act_window'].browse(action_id)
        window_view = request.env['ir.actions.act_window.view'].search([('view_mode', '=', view_mode), ('act_window_id', '=', action_id.id)])
        if not window_view:
            window_view = request.env['ir.actions.act_window.view'].create({'view_mode': view_mode, 'act_window_id': action_id.id})

        window_view.view_id = view_id

        if action_id.xml_id:
            self._edit_model_data(action_id.xml_id)

        return True

    def _edit_model_data(self, xml_id):
        xml_id = xml_id.split('.')
        model_data = request.env['ir.model.data'].search([('module', '=', xml_id[0]), ('name', '=', xml_id[1])])
        model_data.set_studio_modification()

    @http.route('/web_studio/get_studio_view_arch', type='json', auth='user')
    def get_studio_view_arch(self, model, view_type, view_id=False, menu_id=None):
        view_type = 'tree' if view_type == 'list' else view_type  # list is stored as tree in db

        # We have to create a view with the default view if we want to customize it.
        view = self._get_or_create_default_view(model, view_type, view_id)
        studio_view_name = '%s-%s' % (model, view.id)
        module_name = self._create_or_get_module(menu_id)
        studio_view = request.env.ref(module_name + '.' + studio_view_name, raise_if_not_found=False)

        return {
            'view_id': view.id,
            'studio_view_id': studio_view and studio_view.id or False,
            'studio_view_name': studio_view and studio_view_name or False,
            'studio_view_arch': studio_view and studio_view.arch_db or "<data/>",
        }

    @http.route('/web_studio/edit_view', type='json', auth='user')
    def edit_view(self, view_id, studio_view_name, studio_view_arch, operations=None, menu_id=None):
        view = request.env['ir.ui.view'].browse(view_id)

        if not studio_view_name:
            studio_view_name = '%s-%s' % (view.model, view.id)

        module_name = self._create_or_get_module(menu_id)
        studio_view = request.env.ref(module_name + '.' + studio_view_name, raise_if_not_found=False)

        parser = etree.XMLParser(remove_blank_text=True)
        arch = etree.parse(StringIO(studio_view_arch), parser).getroot()

        for op in operations:
            # Call the right operation handler
            if 'node' in op:
                op['node'] = self._preprocess_attrs(op['node'])
            getattr(self, '_operation_%s' % (op['type']))(arch, op, view.model, module_name)

        # Save or create changes into studio view, identifiable by xmlid
        # Example for view id 42 of model crm.lead: web-studio_crm.lead-42
        # TODO: if len(arch) == 0, delete the view
        new_arch = etree.tostring(arch, encoding='utf-8', pretty_print=True)
        if studio_view:
            studio_view.arch_db = new_arch
        else:
            # We have to play with priorities. Consider the following:
            # View Base: <field name="x"/><field name="y"/>
            # View Standard inherits Base: <field name="x" position="after"><field name="z"/></field>
            # View Custo inherits Base: <field name="x" position="after"><field name="x2"/></field>
            # We want x,x2,z,y, because that's what we did in studio, but the order of xpath
            # resolution is sequence,name, not sequence,id. Because "Custo" < "Standard", it
            # would first resolve in x,x2,y, then resolve "Standard" with x,z,x2,y as result.
            studio_view = request.env['ir.ui.view'].create({
                'type': view.type,
                'model': view.model,
                'inherit_id': view.id,
                'mode': 'extension',
                'priority': 99,
                'arch': new_arch,
                'name': "Odoo Studio: %s customization" % (view.name),
            })
            # Create the xmlid of the customization view to append to it later
            request.env['ir.model.data'].create({
                'name': studio_view_name,
                'model': 'ir.ui.view',
                'module': module_name,
                'res_id': studio_view.id,
            })

        fields_view = request.env[view.model].with_context({'studio': True}).fields_view_get(view.id, view.type)

        return fields_view

    @http.route('/web_studio/edit_view_arch', type='json', auth='user')
    def edit_view_arch(self, view_id, view_arch):
        view = request.env['ir.ui.view'].browse(view_id)

        if view:
            view.write({'arch': view_arch})

            if view.xml_id:
                self._edit_model_data(view.xml_id)

            if view.model:
                try:
                    fields_view = request.env[view.model].with_context({'studio': True}).fields_view_get(view.id, view.type)
                    return fields_view
                except Exception:
                    return False

    def _preprocess_attrs(self, node):
        # The js can't give us the field name, it only has the field id
        if node['tag'] == 'field' and 'id' in node['attrs']:
            node['attrs']['name'] = request.env['ir.model.fields'].browse(node['attrs'].pop('id')).name
        return node

    def _get_or_create_default_view(self, model, view_type, view_id=False):
        View = request.env['ir.ui.view']
        # If we have no view_id to inherit from, it's because we are adding
        # fields to the default view of a new model. We will materialize the
        # default view as a true view so we can keep using our xpath mechanism.
        if view_id:
            view = View.browse(view_id)
        else:
            fields_view = request.env[model].fields_view_get(view_id, view_type)
            view = View.create({
                'type': view_type,
                'model': model,
                'arch': fields_view['arch'],
                'name': "Odoo Studio: Default %s view for %s" % (view_type, model),
            })
        return view

    def _node_to_expr(self, node):
        # Format of expr is //tag[@attr1_name=attr1_value][@attr2_name=attr2_value][...]
        expr = '//' + node['tag'] + ''.join(['[@%s=\'%s\']' % (k, v) for k, v in node.get('attrs', {}).items()])

        # Special case when no attrs
        if not node.get('attrs') and node.get('index'):
            expr = expr + '[' + str(node['index']) + ']'

        # Special case when we have <label/><div/> instead of <field>
        # TODO: This is very naive, couldn't the js detect such a situation and
        #       tell us to anchor the xpath on another element ?
        if node['tag'] == 'label':
            expr = expr + '/following-sibling::div'

        return expr

    # If we already have an xpath on this element, use it, otherwise, create a new one.
    def _get_xpath_node(self, arch, operation):
        expr = self._node_to_expr(operation['target'])
        position = operation['position']

        xpath_node = arch.find('xpath[@expr="%s"][@position="%s"]' % (expr, position))
        if xpath_node is None:  # bool(node) == False if node has no children
            xpath_node = etree.SubElement(arch, 'xpath', {
                'expr': expr,
                'position': position
            })

        return xpath_node

    def _operation_remove(self, arch, operation, model=None, module_name=None):
        expr = self._node_to_expr(operation['target'])

        # Did we add this field from studio ? If yes, delete it.
        target_node = arch.find('.' + expr)
        # BEWARE ! What if we added this field from studio but we built
        # other stuff based on that field ? We can't just remove it.
        xpath_node_on_target = arch.find('xpath[@expr="%s"]' % (expr))
        if target_node is not None and xpath_node_on_target is None:  # bool(node) == False if node has no children
            # Check if he is the only one in the parent xpath, if yes, delete the xpath.
            xpath_node = arch.find('.' + expr + '/..')
            if len(xpath_node) == 1:
                arch.remove(xpath_node)
            else:
                xpath_node.remove(target_node)
        else:
            # We have to create a brand new xpath to remove this field from the view.
            # TODO: Sometimes, we have to delete more stuff than just a single tag !
            etree.SubElement(arch, 'xpath', {
                'expr': expr,
                'position': 'replace'
            })

    def _operation_add(self, arch, operation, model, module_name):
        node = operation['node']
        xpath_node = self._get_xpath_node(arch, operation)

        # Create the actual node inside the xpath. It needs to be the first
        # child of the xpath to respect the order in which they were added.
        xml_node = etree.Element(node['tag'], node.get('attrs'))
        if node['tag'] == 'notebook':
            # FIXME take the same randomString as parent
            name = 'studio_page_' + node['attrs']['name'].split('_')[2]
            xml_node_page = etree.Element('page', {'string': 'New Page', 'name': name})
            xml_node.insert(0, xml_node_page)
        elif node['tag'] == 'group':
            xml_node_page_right = etree.Element('group', {'string': 'Right Title', 'name': node['attrs']['name'] + '_right'})
            xml_node_page_left = etree.Element('group', {'string': 'Left Title', 'name': node['attrs']['name'] + '_left'})
            xml_node.insert(0, xml_node_page_right)
            xml_node.insert(0, xml_node_page_left)
        elif node['tag'] == 'button':
            # To create a stat button, we need
            #   - a many2one field (1) that points to this model
            #   - a field (2) that counts the number of records associated with the current record
            #   - an action to jump in (3) with the many2one field (1) as domain/context
            #
            # (1) [button_field] the many2one field
            # (2) [button_count_field] is a non-stored computed field (to always have the good value in the stat button, if access rights)
            # (3) [button_action] an act_window action to jump in the related model
            button_field = request.env['ir.model.fields'].browse(node['field'])
            button_count_field, button_action,  = self._get_or_create_fields_for_button(model, button_field, node['string'], module_name)

            # the XML looks like <button> <field/> </button : a element `field` needs to be inserted inside the button
            xml_node_field = etree.Element('field', {'widget': 'statinfo', 'name': button_count_field.name, 'string': node['string'] or button_count_field.field_description})
            xml_node.insert(0, xml_node_field)

            xml_node.attrib['type'] = 'action'
            xml_node.attrib['name'] = str(button_action.id)
        else:
            xml_node.text = node.get('text')
        xpath_node.insert(0, xml_node)

    def _get_or_create_fields_for_button(self, model, field, button_name, module_name):
        """ Returns the button_count_field and the button_action link to a stat button.
            @param field: a many2one field
        """

        if field.ttype != 'many2one' or field.relation != model:
            raise UserError(_('The related field of a button has to be a many2one to %s.' % model))

        model = request.env['ir.model'].search([('model', '=', model)], limit=1)

        # There is a counter on the button ; as the related field is a many2one, we need
        # to create a new computed field that counts the number of records in the one2many
        button_count_field_name = 'x_%s_count' % field.name
        button_count_field = request.env['ir.model.fields'].search([('name', '=', button_count_field_name), ('model_id', '=', model.id)])
        if not button_count_field:
            button_count_field = request.env['ir.model.fields'].create({
                'name': button_count_field_name,
                'field_description': '%s count' % field.field_description,
                'model': model.model,
                'model_id': model.id,
                'ttype': 'integer',
                'store': False,
                'compute': """for record in self: record['%s'] = self.env['%s'].search_count([('%s', '=', record.id)])""" % (button_count_field_name, field.model, field.name),
            })
            self._create_model_data('new_button_field_%s' % uuid.uuid4(), 'ir.model.fields', button_count_field.id, module_name)

        # Link the button with an associated act_window
        button_action = request.env['ir.actions.act_window'].create({
            'name': button_name,
            'res_model': field.model,
            'view_mode': 'tree,form',
            'view_type': 'form',
            'domain': "[('%s', '=', active_id)]" % (field.name),
            'context': "{'search_default_%s': active_id,'default_%s': active_id}" % (field.name, field.name)
        })
        self._create_model_data('new_button_action_%s' % uuid.uuid4(), 'ir.actions.act_window', button_action.id, module_name)

        return button_count_field, button_action

    def _operation_move(self, arch, operation, model=None, module_name=None):
        self._operation_remove(arch, dict(operation, target=operation['node']))
        self._operation_add(arch, operation)

    # Create or update node for each attribute
    def _operation_attributes(self, arch, operation, model=None, module_name=None):
        ir_model_data = request.env['ir.model.data']
        new_attrs = operation['new_attrs']

        if (new_attrs.get('groups')):
            eval_attr = []
            for many2many_value in new_attrs['groups']:
                group_xmlid = ir_model_data.search([
                    ('model', '=', 'res.groups'),
                    ('res_id', '=', many2many_value)])
                eval_attr.append(group_xmlid.complete_name)
            eval_attr = ",".join(eval_attr)
            new_attrs['groups'] = eval_attr
        else:
            # TOFIX
            new_attrs['groups'] = ''

        xpath_node = self._get_xpath_node(arch, operation)

        for key, new_attr in new_attrs.iteritems():
            xml_node = xpath_node.find('attribute[@name="%s"]' % (key))
            if xml_node is None:
                xml_node = etree.Element('attribute', {'name': key})
                xml_node.text = new_attr
                xpath_node.insert(0, xml_node)
            else:
                xml_node.text = new_attr

    def _operation_chatter(self, arch, operation, model=None, module_name=None):
        def _get_remove_field_op(arch, field_name):
            return {
                'type': 'remove',
                'target': {
                    'tag': 'field',
                    'attrs': {
                        'name': field_name,
                    },
                }
            }

        if not self._is_chatter_allowed(operation['model']):
            # Chatter can only be activated form models that inherit from mail.thread
            return

        # Remove message_ids and message_follower_ids if already defined in form view
        if operation['remove_message_ids']:
            self._operation_remove(arch, _get_remove_field_op(arch, 'message_ids'))
        if operation['remove_follower_ids']:
            self._operation_remove(arch, _get_remove_field_op(arch, 'message_follower_ids'))

        xpath_node = etree.SubElement(arch, 'xpath', {
            'expr': '//sheet',
            'position': 'after',
        })
        chatter_node = etree.Element('div', {'class': 'oe_chatter'})
        thread_node = etree.Element('field', {'name': 'message_ids', 'widget': 'mail_thread'})
        follower_node = etree.Element('field', {'name': 'message_follower_ids', 'widget': 'mail_followers'})
        chatter_node.append(follower_node)
        chatter_node.append(thread_node)
        xpath_node.append(chatter_node)

    def _is_chatter_allowed(self, model):
        # Returns True if the model inherits from mail.thread, False otherwise
        return isinstance(request.env[model], type(request.env['mail.thread']))