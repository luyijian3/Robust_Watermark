import json
import torch
from transformers import GPT2Tokenizer, GPT2LMHeadModel
from transformers import LogitsProcessorList
from transformers import AutoProcessor,LlavaNextForConditionalGeneration
from watermark import WatermarkLogitsProcessor, WatermarkWindow, WatermarkContext
import argparse
import os
from transformers import LlamaTokenizer, AutoModelForCausalLM, AutoTokenizer
from tqdm import tqdm

from util import load_image_local

def main(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model_path = args.llm_path
    
    if args.base_model == 'llava':
        model = LlavaNextForConditionalGeneration.from_pretrained(model_path).to(device)
        processor = AutoProcessor.from_pretrained(model_path) # include processor.tokenizer & processor.image_processor
    else:
        # currently use llava for testing
        pass

    if processor.tokenizer.pad_token_id is None:
        processor.tokenizer.pad_token = processor.tokenizer.eos_token
        model.config.pad_token_id = model.config.eos_token_id

    if args.watermark_type == "window": # use a window of previous tokens to hash, e.g. KGW
        watermark_model = WatermarkWindow(device, args.window_size, processor)
        logits_processor = WatermarkLogitsProcessor(watermark_model)
    elif args.watermark_type == "context":
        watermark_model = WatermarkContext(device, args.chunk_size, processor, delta = args.delta,transform_model_path=args.transform_model, embedding_model=args.embedding_model)
        logits_processor = WatermarkLogitsProcessor(watermark_model)
    else:
        watermark_model, logits_processor = None, None

    with open(args.data_path, 'r') as f:
        lines = f.readlines()

    output = []
    torch.manual_seed(0)
    pbar = tqdm(total=args.generate_number, desc="Generate watermarked text")
    for line in lines:
        #data = json.loads(line)
        #text = data['text']
        image = load_image_local('./test.png')
        text = "[INST] <image>\nWhat is shown in this image? [/INST]"
        words = text.split()

        if len(words) < args.max_new_tokens or len(words)> 2*args.max_new_tokens:
            continue
        
        words = words[:args.prompt_size]
        begin_text = ' '.join(words)
        inputs = processor(begin_text,image, return_tensors="pt").to(device)
        
        generation_config = {
                "max_length": args.max_new_tokens + 10,
                "min_length": args.max_new_tokens - 20,
                "no_repeat_ngram_size": 4,
            }
        if args.decode_method == "sample":
            generation_config["do_sample"] = True
        elif args.decode_method == "beam":
            generation_config["num_beams"] = args.beam_size
            generation_config["do_sample"] = False
        
        if watermark_model is not None:
            generation_config["logits_processor"] = LogitsProcessorList([logits_processor])
        
        print('generating...')

        with torch.no_grad():
            outputs = model.generate(**inputs, **generation_config)
            generated_text = processor.decode(outputs[0], skip_special_tokens=True)
            z_score_generated = watermark_model.detect(generated_text) if watermark_model else 0
            z_score_origin = watermark_model.detect(text) if watermark_model else 0
        print('generated...')
        if len(outputs[0]) > args.max_new_tokens - 20:
            output.append({
                'original_text': text, 
                'generated_text': generated_text,
                'z_score_origin': z_score_origin,
                'z_score_generated': z_score_generated
            })
            pbar.update(1)
        else:
            print('not long enough')
            print(generated_text)
        if len(output) >= args.generate_number:
            break

    with open(args.output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate text using GPT-2 model')
    parser.add_argument('--watermark_type', type=str, default="window")
    parser.add_argument('--base_model', type=str, default="gpt2")
    parser.add_argument('--llm_path', type=str, default="model/gpt2/")
    parser.add_argument('--window_size', type=int, default=0)
    parser.add_argument('--generate_number', type=int, default=200)
    parser.add_argument('--delta', type=float, default=1)
    parser.add_argument('--chunk_size', type=int, default=10)
    parser.add_argument('--max_new_tokens', type=int, default=50)
    parser.add_argument('--data_path', type=str, default="dataset/c4_train_sample.jsonl")
    parser.add_argument('--output_path', type=str, default="text_gpt2_top10.json")
    parser.add_argument('--transform_model', type=str, default="transform_model_cbert6.pth")
    parser.add_argument('--embedding_model', type=str, default="c-bert")
    parser.add_argument('--decode_method', type=str, default="sample")
    parser.add_argument('--prompt_size', type=int, default=5)
    parser.add_argument('--beam_size', type=int, default=5)

    args = parser.parse_args()
    main(args)
