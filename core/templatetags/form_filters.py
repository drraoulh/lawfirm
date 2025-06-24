from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    if hasattr(field, 'as_widget'):
        return field.as_widget(attrs={'class': css_class})
    # If it's not a form field, return it as is (for safe strings)
    return field

@register.filter(name='has_group')
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()
