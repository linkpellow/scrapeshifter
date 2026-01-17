fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Compile the shared proto file into Rust code
    // Railway build: proto file is at ./proto/chimera.proto (copied by Dockerfile)
    // Local dev: proto file is at ../@proto/chimera.proto
    let (proto_path, include_dir) = if std::path::Path::new("./proto/chimera.proto").exists() {
        ("./proto/chimera.proto", "./proto")
    } else if std::path::Path::new("../@proto/chimera.proto").exists() {
        ("../@proto/chimera.proto", "../@proto")
    } else {
        return Err("chimera.proto not found. Expected ./proto/chimera.proto or ../@proto/chimera.proto".into());
    };
    
    tonic_build::configure()
        .build_server(false)  // We're a client, not a server
        .compile_protos(
            &[proto_path],
            &[include_dir],
        )?;
    
    println!("cargo:rerun-if-changed={}", proto_path);
    
    Ok(())
}
