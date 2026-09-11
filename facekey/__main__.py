"""FaceKey CLI — enroll, verify, and manage face profiles."""

import argparse
import sys
import time

import cv2
import numpy as np


def cmd_setup(args):
    """Download models from HuggingFace."""
    from facekey.models import download_models, get_device_info

    print("FaceKey Setup")
    print("=" * 40)

    info = get_device_info()
    print(f"Device: {info['active_provider']}")
    if info["has_cuda"]:
        print("  CUDA GPU detected — GPU acceleration enabled")
    else:
        print("  CPU mode — install onnxruntime-gpu for GPU acceleration")
    print()

    print("Downloading models from HuggingFace...")
    try:
        paths = download_models()
        print()
        print("All models ready:")
        for name, path in paths.items():
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"  {name} ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"Error downloading models: {e}")
        sys.exit(1)

    print()
    print("Setup complete. Run 'facekey enroll' to register your face.")


def cmd_enroll(args):
    """Enroll a face profile by capturing multiple angles."""
    from facekey.camera import Camera
    from facekey.detection import FaceDetector
    from facekey.recognition import FaceEmbedder
    from facekey.storage import EmbeddingVault

    profile_name = args.name or _prompt("Profile name (default: 'default'): ") or "default"
    num_captures = args.captures

    vault = EmbeddingVault()
    if vault.profile_exists(profile_name) and not args.force:
        overwrite = _prompt(f"Profile '{profile_name}' exists. Overwrite? (y/N): ")
        if overwrite.lower() != "y":
            print("Cancelled.")
            return

    print(f"\nEnrolling profile: {profile_name}")
    print(f"Will capture {num_captures} face samples.")
    print("Look at the camera. Move your head slightly between captures.")
    print("Press SPACE to capture, Q to cancel.\n")

    detector = FaceDetector()
    embedder = FaceEmbedder(force_cpu=args.cpu)
    embeddings: list[np.ndarray] = []

    with Camera(index=args.camera) as cam:
        print(f"Camera opened: {cam.actual_resolution}")

        while len(embeddings) < num_captures:
            frame = cam.read()
            display = cv2.flip(frame, 1)

            face = detector.detect_largest(frame)
            status_text = f"Captured: {len(embeddings)}/{num_captures}"

            if face is not None:
                # Draw bbox on mirrored display
                x, y, w, h = face["bbox"]
                fx = display.shape[1] - x - w
                cv2.rectangle(display, (fx, y), (fx + w, y + h), (0, 255, 0), 2)
                cv2.putText(
                    display, f"Score: {face['score']:.2f}",
                    (fx, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                )
                status_text += " | Face detected — press SPACE"
            else:
                status_text += " | No face detected"

            cv2.putText(
                display, status_text,
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
            )
            cv2.imshow("FaceKey Enrollment", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print("Cancelled.")
                cv2.destroyAllWindows()
                return
            elif key == ord(" ") and face is not None:
                aligned = detector.align_face(frame, face["landmarks"])
                embedding = embedder.get_embedding(aligned)
                embeddings.append(embedding)
                print(f"  Captured {len(embeddings)}/{num_captures}")

    cv2.destroyAllWindows()

    if not embeddings:
        print("No faces captured. Enroll cancelled.")
        return

    vault.save_profile(profile_name, embeddings)
    print(f"\nProfile '{profile_name}' enrolled with {len(embeddings)} samples.")
    print("Run 'facekey verify' to test authentication.")


def cmd_verify(args):
    """Run real-time face verification against enrolled profiles."""
    from facekey.auth import AuthPipeline, AuthResult
    from facekey.auth.pipeline import AuthStatus
    from facekey.camera import Camera
    from facekey.storage import EmbeddingVault

    vault = EmbeddingVault()
    profiles = vault.list_profiles()
    if not profiles:
        print("No enrolled profiles. Run 'facekey enroll' first.")
        return

    print(f"Loaded profiles: {', '.join(profiles)}")
    print("Starting verification. Press Q to quit.\n")

    pipeline = AuthPipeline(vault=vault, force_cpu=args.cpu)

    with Camera(index=args.camera) as cam:
        while True:
            frame = cam.read()
            result = pipeline.authenticate_frame(frame)
            display = cv2.flip(frame, 1)

            color, label = _status_display(result)

            cv2.putText(
                display, label,
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2,
            )

            if result.similarity > 0:
                cv2.putText(
                    display, f"Similarity: {result.similarity:.3f}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                )
            if result.spoof_score > 0:
                cv2.putText(
                    display, f"Real score: {result.spoof_score:.3f}",
                    (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                )

            details = result.details
            if details.get("face_detected"):
                blinks = details.get("blink_count", 0)
                cv2.putText(
                    display, f"Blinks: {blinks} | Liveness: {'PASS' if result.liveness_passed else 'pending...'}",
                    (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                )

            cv2.putText(
                display, f"{result.elapsed_ms:.0f}ms",
                (display.shape[1] - 80, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1,
            )

            cv2.imshow("FaceKey Verify", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cv2.destroyAllWindows()
    print("Verification stopped.")


def cmd_profiles(args):
    """List or delete enrolled profiles."""
    from facekey.storage import EmbeddingVault

    vault = EmbeddingVault()

    if args.delete:
        if vault.delete_profile(args.delete):
            print(f"Deleted profile: {args.delete}")
        else:
            print(f"Profile not found: {args.delete}")
        return

    profiles = vault.list_profiles()
    if not profiles:
        print("No enrolled profiles.")
    else:
        print("Enrolled profiles:")
        for name in profiles:
            embeddings = vault.load_profile(name)
            print(f"  {name} ({len(embeddings)} samples)")


def cmd_benchmark(args):
    """Run a quick benchmark of the ML pipeline."""
    from facekey.camera import Camera
    from facekey.detection import FaceDetector
    from facekey.models import get_device_info
    from facekey.recognition import FaceEmbedder
    from facekey.antispoof import AntiSpoof

    info = get_device_info()
    print(f"Device: {info['active_provider']}")
    print(f"Benchmarking {args.frames} frames...\n")

    detector = FaceDetector()
    embedder = FaceEmbedder(force_cpu=args.cpu)
    antispoof = AntiSpoof(force_cpu=args.cpu)

    detect_times = []
    embed_times = []
    spoof_times = []
    total_times = []

    with Camera(index=args.camera) as cam:
        for i in range(args.frames):
            frame = cam.read()
            t_total = time.perf_counter()

            t0 = time.perf_counter()
            face = detector.detect_largest(frame)
            detect_times.append((time.perf_counter() - t0) * 1000)

            if face is not None:
                aligned = detector.align_face(frame, face["landmarks"])

                t0 = time.perf_counter()
                embedder.get_embedding(aligned)
                embed_times.append((time.perf_counter() - t0) * 1000)

                t0 = time.perf_counter()
                antispoof.predict(frame, face["bbox"])
                spoof_times.append((time.perf_counter() - t0) * 1000)

            total_times.append((time.perf_counter() - t_total) * 1000)

    print("Results (ms):")
    print(f"  Detection:    avg={_avg(detect_times):.1f}  p50={_p50(detect_times):.1f}  p95={_p95(detect_times):.1f}")
    if embed_times:
        print(f"  Embedding:    avg={_avg(embed_times):.1f}  p50={_p50(embed_times):.1f}  p95={_p95(embed_times):.1f}")
    if spoof_times:
        print(f"  Anti-spoof:   avg={_avg(spoof_times):.1f}  p50={_p50(spoof_times):.1f}  p95={_p95(spoof_times):.1f}")
    print(f"  Total/frame:  avg={_avg(total_times):.1f}  p50={_p50(total_times):.1f}  p95={_p95(total_times):.1f}")
    print(f"  FPS:          ~{1000 / _avg(total_times):.1f}")


def cmd_gui_enroll(args):
    """Launch the GUI enrollment window."""
    from facekey.gui.enrollment import run_enrollment
    run_enrollment(force_cpu=args.cpu, camera_index=args.camera)


def cmd_gui_verify(args):
    """Launch the GUI verification window."""
    from facekey.gui.verify import run_verify
    run_verify(force_cpu=args.cpu, camera_index=args.camera)


def cmd_tray(args):
    """Launch the system tray app."""
    from facekey.gui.tray import run_tray
    run_tray(force_cpu=args.cpu, camera_index=args.camera)


def cmd_auth_window(args):
    """Launch the quick auth window."""
    from facekey.gui.auth_window import run_auth
    run_auth(
        force_cpu=args.cpu,
        camera_index=args.camera,
        timeout=args.timeout,
        pipe_output=args.pipe_output,
    )


def cmd_service(args):
    """Start the named pipe auth service."""
    from facekey.service.pipe_server import run_service
    run_service(force_cpu=args.cpu, camera_index=args.camera)


def _status_display(result) -> tuple:
    from facekey.auth.pipeline import AuthStatus
    status_map = {
        AuthStatus.SUCCESS: ((0, 255, 0), "MATCH"),
        AuthStatus.NO_FACE: ((128, 128, 128), "No face"),
        AuthStatus.NO_MATCH: ((0, 0, 255), "No match"),
        AuthStatus.SPOOF_DETECTED: ((0, 0, 255), "SPOOF DETECTED"),
        AuthStatus.LOCKED_OUT: ((0, 0, 255), "LOCKED OUT"),
        AuthStatus.LIVENESS_FAILED: ((0, 165, 255), "Liveness failed"),
    }
    color, label = status_map.get(result.status, ((255, 255, 255), str(result.status)))
    if result.profile_name:
        label += f" — {result.profile_name} ({result.similarity:.2f})"
    return color, label


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _avg(vals): return sum(vals) / len(vals) if vals else 0
def _p50(vals): return sorted(vals)[len(vals) // 2] if vals else 0
def _p95(vals): return sorted(vals)[int(len(vals) * 0.95)] if vals else 0


def main():
    parser = argparse.ArgumentParser(
        prog="facekey",
        description="FaceKey — Face unlock for Windows using any RGB webcam",
    )
    parser.add_argument("--cpu", action="store_true", help="Force CPU inference (skip GPU)")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Download models from HuggingFace")

    enroll = sub.add_parser("enroll", help="Enroll a face profile")
    enroll.add_argument("--name", type=str, help="Profile name")
    enroll.add_argument("--captures", type=int, default=5, help="Number of face samples (default: 5)")
    enroll.add_argument("--force", action="store_true", help="Overwrite existing profile")

    sub.add_parser("verify", help="Run real-time face verification")

    profiles = sub.add_parser("profiles", help="List or delete profiles")
    profiles.add_argument("--delete", type=str, help="Delete a profile by name")

    bench = sub.add_parser("benchmark", help="Benchmark pipeline performance")
    bench.add_argument("--frames", type=int, default=100, help="Number of frames to benchmark")

    sub.add_parser("gui-enroll", help="Enroll via GUI (CustomTkinter)")
    sub.add_parser("gui-verify", help="Verify via GUI (CustomTkinter)")
    sub.add_parser("tray", help="Launch system tray app")

    auth_win = sub.add_parser("auth-window", help="Quick face auth popup")
    auth_win.add_argument("--timeout", type=int, default=15, help="Auth timeout in seconds")
    auth_win.add_argument("--pipe-output", action="store_true", help="Print JSON result to stdout")

    sub.add_parser("service", help="Start named pipe auth service")

    args = parser.parse_args()

    commands = {
        "setup": cmd_setup,
        "enroll": cmd_enroll,
        "verify": cmd_verify,
        "profiles": cmd_profiles,
        "benchmark": cmd_benchmark,
        "gui-enroll": cmd_gui_enroll,
        "gui-verify": cmd_gui_verify,
        "auth-window": cmd_auth_window,
        "tray": cmd_tray,
        "service": cmd_service,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
