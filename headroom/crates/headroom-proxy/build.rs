fn main() {
    cc::Build::new()
        .file("compat.c")
        .compile("compat");
}
