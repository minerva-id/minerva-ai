# Stage 1: Build Stage
FROM rust:1.86-slim-bookworm AS builder

# Install system dependencies needed for compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# Copy dependency definition to cache compile stage
COPY Cargo.toml Cargo.lock ./

# Create dummy source file to compile dependencies first (caching)
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release
RUN rm -rf src

# Copy real source code and build actual binary
COPY src ./src
RUN touch src/main.rs
RUN cargo build --release

# Stage 2: Runtime Stage
FROM debian:bookworm-slim AS runner

# Install runtime dependencies (OpenSSL, CA-Certificates, SQLite-related)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    ca-certificates \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary from builder
COPY --from=builder /usr/src/app/target/release/minerva-ai /app/minerva-ai

# Copy entrypoint/run script if needed (otherwise run directly)
CMD ["/app/minerva-ai"]
