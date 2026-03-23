from __future__ import annotations


def main() -> None:
    attention_heads = 64
    tensor_parallel_size = 4
    model_params_billion = 72
    bytes_per_param_bf16 = 2
    gib = 1024**3

    if attention_heads % tensor_parallel_size != 0:
        raise ValueError(
            "Invalid tensor parallel configuration: "
            f"{attention_heads} heads not divisible by {tensor_parallel_size}."
        )

    heads_per_gpu = attention_heads // tensor_parallel_size
    total_bytes = model_params_billion * (10**9) * bytes_per_param_bf16
    total_gib = total_bytes / gib
    per_gpu_gib = total_gib / tensor_parallel_size

    print("Qwen2.5-72B tensor parallel sanity check")
    print(f"Attention heads: {attention_heads}")
    print(f"Tensor parallel size: {tensor_parallel_size}")
    print(f"Heads per GPU: {heads_per_gpu}")
    print(f"Estimated model weights (BF16): {total_gib:.2f} GiB (~144 GB)")
    print(f"Estimated weights per GPU: {per_gpu_gib:.2f} GiB")
    print("Additional VRAM is required for KV cache and runtime buffers.")


if __name__ == "__main__":
    main()
