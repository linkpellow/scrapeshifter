# Chimera Core - Rust Worker Swarm
FROM rust:1.75-slim as builder

WORKDIR /app

# Install protobuf compiler
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests
COPY Cargo.toml Cargo.lock* ./
COPY build.rs ./

# Copy proto file from build context (proto file is in chimera-core/ directory)
# Railway build context is chimera-core/, so proto file must be in this directory
# We copy it from proto.chimera.proto (copied from @proto/ during git commit)
COPY proto.chimera.proto ./proto/chimera.proto

# Copy source
COPY src ./src

# Build release binary
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy binary from builder
COPY --from=builder /app/target/release/chimera-worker /app/chimera-worker

# Set environment
ENV RUST_LOG=info
ENV RAILWAY_ENVIRONMENT=production

# Run the worker
CMD ["/app/chimera-worker"]
