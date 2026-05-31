"""Auto load-more when the user scrolls near the bottom of the home feed."""

from __future__ import annotations

import streamlit.components.v1 as components


def inject_home_infinite_scroll(*, button_label: str = "Load more recipes") -> None:
    """
    Clicks the Streamlit load-more button when the sentinel enters view.
    Place ``st.markdown('<div id="home-feed-sentinel"></div>', ...)`` above the button first.
    """
    label = button_label.replace("\\", "\\\\").replace("'", "\\'")
    components.html(
        f"""
        <script>
        (function () {{
          const LABEL = '{label}';
          let busy = false;
          const clickLoadMore = () => {{
            if (busy) return;
            const doc = window.parent.document;
            const buttons = doc.querySelectorAll('button');
            for (const btn of buttons) {{
              const text = (btn.innerText || '').trim();
              if (text === LABEL) {{
                busy = true;
                btn.click();
                setTimeout(() => {{ busy = false; }}, 1200);
                return;
              }}
            }}
          }};
          const attach = () => {{
            const sentinel = window.parent.document.getElementById('home-feed-sentinel');
            if (!sentinel) return;
            const io = new IntersectionObserver(
              (entries) => {{
                if (entries[0] && entries[0].isIntersecting) clickLoadMore();
              }},
              {{ root: null, rootMargin: '320px', threshold: 0.01 }}
            );
            io.observe(sentinel);
          }};
          attach();
          setTimeout(attach, 400);
        }})();
        </script>
        """,
        height=0,
    )
