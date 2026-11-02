FROM rust:1-bookworm AS builder
WORKDIR /build
COPY services/ledger-rust/ ./
RUN cargo build --release --features service

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 10002 -s /usr/sbin/nologin loyalty
COPY --from=builder /build/target/release/ithute-loyalty-ledger /usr/local/bin/ledger
USER loyalty
EXPOSE 8090
ENTRYPOINT ["/usr/local/bin/ledger"]
