from branca.element import MacroElement, Template, Element, Figure

class JavaScript(MacroElement):
  """
  Creates a small snippet of raw JavaScript.

  Parameters
  ----------
  script: string, representing the JavaScript code to insert in the html file
  html: string, representing html code to insert in the <body> section of the html file
  args: dict, mapping between python vars and folium vars

  """
  _template = Template(
    u"""{% macro html(this, args) %}
        {{this.html.render(**this.args)}}
        {% endmacro %}
        {% macro script(this, args) %}
        {{this.script.render(**this.args)}}
        {% endmacro %}"""
  )

  def __init__(self, script=None, html=None, args=None):
    super(JavaScript, self).__init__()
    self.script = Element(script)
    self.html = Element(html)
    self._name = "JavaScript"
    if args is None:
        args = {}
    self.args = args

def render_nodes(node, parent):
  mf = Figure()
  mf._name=parent._name
  mf._id = parent._id
  mf._template = Template(
          '{{this.script.render(**kwargs)}}\n'
      )

  node.add_to(mf)
  html = mf.render()
  html = "".join([s for s in html.splitlines(True) if s.strip("\r\n")])
  return html
