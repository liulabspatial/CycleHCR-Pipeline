arg = getArgument();
print("Stitching");

args = split(arg, ";;");

print(args[0]);

run("Fuse dataset ...", args[0]);

print("Image Fusion DONE.");
eval("script", "System.exit(0);");
run("Quit");