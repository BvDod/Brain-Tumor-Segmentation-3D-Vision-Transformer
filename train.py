
import torch
import monai
import os

from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

from CustomDataset.brats_dataset import BratsDataset
from functions.transforms import get_transforms_3d
from models.vit3d import VIT3Dsegmentation
from functions.visualize import add_segmentation_to_image


def train(settings):
    writer = SummaryWriter()    # Tensorboard for logging

    # Print settings and info
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(str(settings))
    print(f"Device: {device}" + "\n")

    # Loading dataset
    transforms = get_transforms_3d(settings["model_settings"]["patch_size"])
    dataset = BratsDataset(transforms=transforms, device=device)
    dataset_train, _ = torch.utils.data.random_split(dataset, [0.8, 0.2])

    dataloader_train = DataLoader(dataset_train, batch_size=settings["batch_size"], shuffle=True, drop_last=True, pin_memory=False, num_workers = 6)
    
    train_sample = dataset_train[0]
    input_shape, mask_shape = train_sample["image"].shape, train_sample["label"].shape

    # Setting up model
    model_settings = settings["model_settings"]
    model_settings["num_channels"] = input_shape[0]
    model_settings["input_shape"] = input_shape
    model_settings["device"] = device
 
    model = VIT3Dsegmentation(model_settings)
    model.to(device)

    # Continue training from checkpoint
    if settings["continue_training"]:
        model.load_state_dict(torch.load("models/saved_models/model_latest.pt", weights_only=True)) 

    # We use higher momentum beta because of low batch size
    optimizer = torch.optim.Adam(model.parameters(), lr=settings["learning_rate"], weight_decay=1e-5, betas=(0.99, 0.999))
    
    # Combines dice and cross entropy loss
    loss_function = monai.losses.DiceCELoss(softmax=True)
    
    scaler = torch.amp.GradScaler("cuda" ,enabled=True)
    best_loss = None
   
    # Training loop
    train_losses, test_losses = [], []
    for epoch in range(settings["max_epochs"]):
        
        train_losses_epoch = []
        
        print(f"Epoch: {epoch}/{settings["max_epochs"]}")
        model.train()
        for batch_i, train_sample in enumerate(dataloader_train):
            x_train, y_train = train_sample["image"], train_sample["label"], 
            x_train, y_train = x_train.to(device), y_train.to(device)
            
            with torch.autocast(device_type=device, dtype=torch.float16, enabled=True):
                res = model(x_train)
                loss = loss_function(res, y_train)
                train_losses_epoch.append(loss.item())
                loss = loss / settings["batch_accumulation_iter"] # scale loss to batch size
            
            scaler.scale(loss).backward()

            # weights update if batch_accumulation_iter is reached
            if ((batch_i + 1) % settings["batch_accumulation_iter"] == 0) or (batch_i + 1 == len(dataloader_train)):
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
            
            writer.add_scalar("Loss/train (iteration)", train_losses_epoch[-1], epoch*len(dataloader_train) + batch_i)

            # Log sample segmentation image every 10th batch
            if batch_i % 10 == 0:
                pred = res.detach().movedim(1,-1).argmax(dim=-1)
                images = add_segmentation_to_image(x_train[0].detach().cpu(), pred[0].cpu())
                writer.add_images(f"Original", images, epoch*len(dataloader_train) + batch_i)

            
        print(f"Train loss: {sum(train_losses_epoch) / len(train_losses_epoch)}")
        train_losses.append(sum(train_losses_epoch) / len(train_losses_epoch))
        writer.add_scalar("Loss/train", train_losses[-1], epoch)

        # Save model every epoch
        path = f"models/saved_models/"
        os.makedirs(path, exist_ok = True) 
        torch.save(model.state_dict(), path + "model_latest.pt")
        
        # Save best model
        if train_losses[-1] < best_loss:
            torch.save(model.state_dict(), path + f"model_best({epoch}).pt")
            best_loss = train_losses[-1]

        """
        #  Early stopping
        epoch_delta = settings["early_stopping_epochs"]
        if len(train_losses) > epoch_delta and max(train_losses[-epoch_delta:-1]) < train_losses[-1]:
            print("Early stopping")
            break
        
        # Evaluation
        model.eval()
        with torch.no_grad():
            test_losses_epoch = []
            val_corrects = 0
            for x_test, y_test in dataloader_test:
                x_test, y_test = x_test.to(device), y_test.to(device)
                output = model(x_test)
                loss = loss_function(output, y_test)
                test_losses_epoch.append(loss.item())

                _, val_preds = torch.max(output, 1)
                val_corrects += torch.sum(val_preds == y_test)
            print(f"Test loss: {sum(test_losses_epoch) / len(test_losses_epoch)}")
            test_losses.append(sum(test_losses_epoch) / len(test_losses_epoch))

            print(f"Test acc: {val_corrects / len(dataloader_test.dataset)}")
            
            writer.add_scalar("Loss/test", test_losses[-1], epoch)
            writer.add_scalar("ACC/test", val_corrects / len(dataloader_test.dataset), epoch)
        """
              

if __name__ == "__main__":
    settings = {
        "batch_size": 2,
        "learning_rate": 1e-4, # for Mnsist
        "max_epochs": 100,
        "early_stopping_epochs": 50,

        "batch_accumulation_iter": 1,

        "continue_training": False,

        "model_settings" : {
            "patch_size": 32,
            "embedding_size": 256,
            "attention_heads": 8,
            "transformer_layers": 8,
            "output_classes": 5,
        }
        
    }
    train(settings)