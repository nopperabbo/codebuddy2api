FROM --platform=linux/amd64 golang:1.24-alpine AS build
WORKDIR /src
RUN printf '#!/bin/sh\necho hello\n' > /out && chmod +x /out

FROM --platform linux/amd64 gcr.io/distroless/static-debian11:nonroot AS runtime
COPY --from=build /out /out
ENTRYPOINT ["/out"]
