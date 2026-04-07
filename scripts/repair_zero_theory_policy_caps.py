from decimal import Decimal
from apps.results.models import ResultSheet
from apps.results.entry_flow import sheet_policy_state, _policy_limit_for_sheet, decimal_text, decimal_value
import json

changed = []
for sheet in ResultSheet.objects.select_related('academic_class','subject').all():
    policies = sheet_policy_state(sheet)
    updated = False
    for key in ('ca1','ca23','ca4','exam'):
        section = policies.get(key, {})
        if not section.get('enabled'):
            continue
        objective_max = decimal_value(section.get('objective_max'))
        theory_max = decimal_value(section.get('theory_max'))
        if theory_max == Decimal('0.00'):
            limit = _policy_limit_for_sheet(key, sheet)
            replacement = max(Decimal('0.00'), (limit - objective_max).quantize(Decimal('0.01')))
            if replacement > Decimal('0.00'):
                section['theory_max'] = decimal_text(replacement)
                policies[key] = section
                updated = True
                changed.append({'sheet_id': sheet.id, 'class': sheet.academic_class.code, 'subject': sheet.subject.name, 'component': key, 'objective_max': str(objective_max), 'new_theory_max': section['theory_max']})
    if updated:
        sheet.cbt_component_policies = policies
        sheet.save(update_fields=['cbt_component_policies','updated_at'])
print(json.dumps({'changed_count': len(changed), 'changed': changed}, default=str))
