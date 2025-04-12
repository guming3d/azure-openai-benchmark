# Generate Input Prompt Tool

---

## English Section

This Python tool generates JSON prompts for load testing. It supports multimodal requests combining text and image inputs, as well as text-only requests.

---

### Prerequisites

1. **Install Python**
   Ensure you have Python 3.10 or later installed on your system.

2. **Install Required Packages**
   We recommend using a virtual environment. Use the steps below to set up a virtual environment and install the required Python packages:

   #### Create a Virtual Environment
   ```bash
   python -m venv .venv
   ```

   #### Activate the Virtual Environment

   - On **Linux/macOS**:
     ```bash
     source .venv/bin/activate
     ```

   - On **Windows**:
     ```bash
     .venv\Scripts\activate
     ```

   #### Install the Required Packages
   ```bash
   pip install pillow
   ```

---

### Setup

#### Step 1: Clone the Repository
```bash
git clone https://github.com/guming3d/azure-openai-benchmark
cd azure-openai-benchmark/tools
```

#### Step 2: Prepare Image Directory

Place the images you want to use in a directory under `tools`. Supported image formats are `.jpg`, `.jpeg`, and `.png`.

---

### Usage

Run the script with the following command:

```bash
python tools/generate_input_prompt.py --image-dir tools/images --request-ratio 0.5 --output-file prompt-output-0.5.json --quality-mode high --total-messages 100
```

---

### Command Arguments

| Parameter          | Description                                                  |
|--------------------|--------------------------------------------------------------|
| `--image-dir`      | Path to the directory containing images                      |
| `--request-ratio`  | Ratio of multimodal requests (0.0 to 1.0)                    |
| `--output-file`    | Output file path                                             |
| `--quality-mode`   | Image quality mode: `low` or `high` (Optional)               |
| `--total-messages` | Total number of messages to generate (Optional)              |

---

### Error Handling

- If the `--request-ratio` is outside the range of 0.0 to 1.0, an error will be thrown:
  ```
  Error: --request-ratio must be between 0.0 and 1.0 (inclusive).
  ```

- If no images are found in the image directory, an error will be thrown:
  ```
  Error: No image files found in '<image_dir>'.
  ```

---

### Output

The script generates a JSON file containing the prompts you requested at the specified output file path.

---

### Contact

For any issues or questions, feel free to [open an Issue](https://github.com/guming3d/azure-openai-benchmark/issues).

---

## 中文部分

---

### 工具简介

此 Python 工具用于生成用于负载测试的 JSON 提示。支持结合文本和图像输入的多模态请求，同时也支持仅文本请求。

---

### 环境准备

1. **安装 Python**
   确保系统已安装 Python 3.10 或更高版本。

2. **安装依赖包**
   推荐使用虚拟环境。使用以下步骤设置虚拟环境并安装所需的 Python 包：

   #### 创建虚拟环境
   ```bash
   python -m venv .venv
   ```

   #### 激活虚拟环境

   - 在 **Linux/macOS**:
     ```bash
     source .venv/bin/activate
     ```

   - 在 **Windows**:
     ```bash
     .venv\Scripts\activate
     ```

   #### 安装依赖包
   ```bash
   pip install pillow
   ```

---

### 使用步骤

#### 步骤 1：克隆代码仓库
```bash
git clone https://github.com/guming3d/azure-openai-benchmark
cd azure-openai-benchmark
```

#### 步骤 2：准备图片目录

将需要使用的图片放入 `tools` 下的一个目录中。支持 `.jpg`、`.jpeg` 和 `.png` 格式的图片。

---

### 使用说明

运行以下命令以生成所需的提示：

```bash
python tools/generate_input_prompt.py --image-dir tools/images --request-ratio 0.5 --output-file prompt-output-0.5.json --quality-mode high --total-messages 100
```

---

### 命令参数

| 参数名称             | 参数描述                     |
|--------------------|-----------------------------|
| `--image-dir`      | 图片目录路径                 |
| `--request-ratio`  | 多模态请求比例（0.0 至 1.0）        |
| `--output-file`    | 输出文件路径                  |
| `--quality-mode`   | 图像质量模式：`low` 或 `high` (可选) |
| `--total-messages` | 生成消息的总数量 (可选)           |

---

### 错误处理

- 如果 `--request-ratio` 超出范围 (0.0 至 1.0)，脚本将抛出错误：
  ```
  Error: --request-ratio must be between 0.0 and 1.0 (inclusive).
  ```

- 如果图片目录中未找到任何图片，脚本将抛出错误：
  ```
  Error: No image files found in '<图片目录路径>'.
  ```

---

### 输出结果

脚本将生成包含您所请求提示的 JSON 文件，保存到您通过 `--output-file` 参数指定的路径中。

---

### 联系方式

如有任何问题或建议，请提交 [Issue](https://github.com/guming3d/azure-openai-benchmark/issues)。 