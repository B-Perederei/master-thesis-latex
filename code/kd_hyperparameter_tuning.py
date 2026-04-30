import optuna
import subprocess
import os
import sys

def objective(trial):
    # script.py gpu_id
    gpu_id = sys.argv[1] if len(sys.argv) > 1 else "0"

    # 2. Define the continuous search space
    t = trial.suggest_float("t", 1.5, 8) 
    alpha = trial.suggest_float("alpha", 0.1, 0.9)

    # 3. Define the categorical search space for the Teacher Model
    # Optuna will choose one of these integer values
    teacher_bits = trial.suggest_categorical("teacher_bits", [3, 4, 6])
    
    base_path = "checkpoint/resnet32/cifar100/"
    teacher_configs = {
        3: f"{base_path}ResNet-32_CIFAR-100_INT3_SPARSITY90.pth",
        4: f"{base_path}ResNet-32_CIFAR-100_INT4_SPARSITY90.pth",
        6: f"{base_path}ResNet-32_CIFAR-100_INT6_SPARSITY90.pth"
    }
    
    selected_teacher_path = teacher_configs[teacher_bits]
    teacher_bit_str = str(teacher_bits)

    # 4. Set up dynamic save paths
    trial_num = trial.number
    save_model_path = f"OPTUNA_TRIAL{trial_num}_ResNet-32_CIFAR-100_T{t:.2f}_alpha{alpha:.2f}_TeacherINT{teacher_bits}.pth"
    test_acc_path = f"results/test_accuracy_trial{trial_num}.txt"
    train_acc_path = f"results/train_accuracy_trial{trial_num}.txt"

    # 5. Construct the bash command, dynamically inserting the teacher configs
    cmd = [
        "python", "cifar_train.py", "cifar100", 
        "--datapath", "./data", "-a", "resnet", "--layers", "32", "-C", "-g", "0", 
        "--save", save_model_path, 
        "-P", "--prune-type", "unstructured", "--method", "distill", 
        "--prune-freq", "8", "--prune-rate", "0.9", "--prune-imp", "L2", 
        "--epochs", "163", 
        "--batch-size", "128", "--lr", "0.2", "--wd", "1e-4", 
        "--nesterov", "--scheduler", "multistep", "--milestones", "80", "123", 
        "--gamma", "0.1", "--target_epoch", "123", 
        "--cu_num", gpu_id,
        "--n_bits", "2", "--acti_quan", "1", "--acti_n_bits", "2", 
        "--txt_name_test", test_acc_path, 
        "--txt_name_train", train_acc_path, 
        "--run-type", "train", 
        "--teacher_path", selected_teacher_path,
        "--n_bits_teacher", teacher_bit_str,
        "--acti_n_bits_teacher", teacher_bit_str,
        "--layers_teacher", "32", 
        "--kd_phase", "full", "--kd_method", "kd", 
        "--t", str(t), "--alpha", str(alpha),
        "--trial_num", str(trial_num)
    ]

    print(f"\n--- Worker GPU {gpu_id} | Trial {trial_num} | Teacher INT{teacher_bits} | T={t:.3f} | Alpha={alpha:.3f} ---")
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise optuna.TrialPruned()

    try:
        with open(test_acc_path, "r") as f:
            lines = f.readlines()
            last_20_lines = lines[-60:]
            last_20_accs = [float(line.strip()) for line in last_20_lines if line.strip()]
            best_accuracy = max(last_20_accs)
            
            print(f"--> Trial {trial_num} Best Acc in last 60 epochs: {best_accuracy}%")
            
    except Exception as e:
        print(f"Error reading accuracy file for trial {trial_num}: {e}")
        return 0.0

    return best_accuracy

if __name__ == "__main__":
    study = optuna.create_study(
        study_name="kd_cifar-100_hyperparameters",
        storage="sqlite:///kd_study.db",
        load_if_exists=True,
        direction="maximize"
    )
    
    study.optimize(objective, n_trials=15)