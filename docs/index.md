---
layout: default
---

# Bitácora de NeuroGate

Estoy construyendo un **"antivirus neuronal"**: la capa de seguridad que se
sienta entre una señal cerebral y las aplicaciones que quieren consumirla —
permisos por app, detección de anomalías, cifrado y un registro auditable
imposible de alterar en silencio. Cuando los BCI de consumo lleguen, esta capa
estará lista desde el primer día.

Aquí documento el proceso, capa a capa, para quien le llegue o le interese.

## Entradas

<ul class="post-list">
{% for post in site.posts %}
  <li>
    <time>{{ post.date | date: "%d·%m·%Y" }}</time>
    <a href="{{ post.url | relative_url }}">{{ post.title }}</a>
    {% if post.description %}<p>{{ post.description }}</p>{% endif %}
  </li>
{% endfor %}
</ul>
