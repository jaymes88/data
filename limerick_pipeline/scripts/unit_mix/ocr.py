import subprocess, sys, os, tempfile, glob
def ocr(pdf, first=1, last=None, dpi=150):
    d = tempfile.mkdtemp(dir='eplan')
    args = ['pdftoppm', '-r', str(dpi), '-gray', '-f', str(first)] + (['-l', str(last)] if last else []) + [pdf, f'{d}/p']
    subprocess.run(args, check=True, capture_output=True)
    out = []
    for img in sorted(glob.glob(f'{d}/p*.pgm')):
        t = subprocess.run(['tesseract', img, '-', '--psm', '6'], capture_output=True, text=True, env={**os.environ, 'OMP_THREAD_LIMIT': '1'}, timeout=120).stdout
        out.append(f'--- page {img[-7:-4]}\n{t}')
    return '\n'.join(out)
if __name__ == '__main__':
    print(ocr(sys.argv[1], *(int(x) for x in sys.argv[2:])))
