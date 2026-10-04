from django import template


register = template.Library()


@register.simple_tag
def querystring(params, key, value):
    """
    Usage: {% querystring request.GET 'page' 2 %}
    Returns an encoded querystring with one key replaced/added.
    """
    q = params.copy()
    q[key] = value
    return q.urlencode()

