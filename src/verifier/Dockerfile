# ==============================================================================
# Custom Branded Inji Verify UI
# ==============================================================================
# Extends upstream injistack/inji-verify-ui:0.17.0 with custom AIT branding:
# - Replaces default Inji logo with AIT Verify SVG logo
# - Injects custom AIT theme stylesheet (custom teal brand colors)
# ==============================================================================
FROM injistack/inji-verify-ui:0.17.0

# Copy custom AIT branding logo and assets
COPY src/verifier/assets/inji_verify.svg /usr/share/nginx/html/assets/images/inji_verify.svg

# Inject custom theme stylesheet into index.html
COPY src/verifier/theme.css /usr/share/nginx/html/theme.css
RUN sed -i 's|</head>|<link rel="stylesheet" href="/theme.css"></head>|' /usr/share/nginx/html/index.html
